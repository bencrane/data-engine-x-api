# modal_app/flows/pipeline_runner.py — Prefect flow that waterfalls through steps

import os
from typing import Any

from prefect import flow, task
from supabase import create_client

import modal


@task(retries=2, retry_delay_seconds=5)
def load_submission(submission_id: str) -> dict:
    """Load submission data from Supabase."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    result = (
        client.table("submissions")
        .select("*, recipes(*)")
        .eq("id", submission_id)
        .single()
        .execute()
    )
    return result.data


@task(retries=2, retry_delay_seconds=5)
def load_recipe_steps(recipe_id: str) -> list[dict]:
    """Load recipe steps with their Modal function names."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    result = (
        client.table("recipe_steps")
        .select("*, steps(*)")
        .eq("recipe_id", recipe_id)
        .order("order")
        .execute()
    )
    return result.data


@task
def create_pipeline_run(submission_id: str, org_id: str) -> str:
    """Create a pipeline run record."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    result = (
        client.table("pipeline_runs")
        .insert({
            "submission_id": submission_id,
            "org_id": org_id,
            "status": "running",
        })
        .execute()
    )
    return result.data[0]["id"]


@task
def update_pipeline_status(pipeline_run_id: str, status: str) -> None:
    """Update pipeline run status."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    client.table("pipeline_runs").update({"status": status}).eq(
        "id", pipeline_run_id
    ).execute()


@task
def save_step_result(
    pipeline_run_id: str,
    step_id: str,
    step_order: int,
    status: str,
    output_data: Any = None,
    error_message: str | None = None,
) -> None:
    """Save step execution result."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    client.table("step_results").insert({
        "pipeline_run_id": pipeline_run_id,
        "step_id": step_id,
        "step_order": step_order,
        "status": status,
        "output_data": output_data,
        "error_message": error_message,
    }).execute()


@task(retries=1)
def execute_modal_step(
    function_name: str,
    input_data: list[dict[str, Any]],
    step_config: dict | None = None,
) -> list[dict[str, Any]]:
    """Execute a Modal function and return its output."""
    # Look up the Modal function by name
    modal_app = modal.App.lookup("data-engine-x")
    step_fn = modal_app[function_name]

    # Call the function remotely
    if step_config:
        result = step_fn.remote(input_data, **step_config)
    else:
        result = step_fn.remote(input_data)

    return result


@flow(name="pipeline-runner")
def run_pipeline(submission_id: str) -> dict:
    """
    Main pipeline flow that processes a submission through its recipe steps.

    1. Load submission and recipe
    2. Create pipeline run record
    3. Execute each step in sequence (waterfall)
    4. Save results after each step
    5. Update final status
    """
    # Load submission data
    submission = load_submission(submission_id)
    recipe_steps = load_recipe_steps(submission["recipe_id"])

    # Create pipeline run
    pipeline_run_id = create_pipeline_run(
        submission_id=submission_id,
        org_id=submission["org_id"],
    )

    # Start with submission data
    current_data = submission["data"]
    all_successful = True

    # Execute each step in sequence
    for recipe_step in recipe_steps:
        step = recipe_step["steps"]
        step_order = recipe_step["order"]
        step_config = recipe_step.get("config")

        try:
            # Execute the Modal function
            output_data = execute_modal_step(
                function_name=step["modal_function_name"],
                input_data=current_data,
                step_config=step_config,
            )

            # Save successful result
            save_step_result(
                pipeline_run_id=pipeline_run_id,
                step_id=step["id"],
                step_order=step_order,
                status="completed",
                output_data=output_data,
            )

            # Use output as input for next step
            current_data = output_data

        except Exception as e:
            # Save failed result
            save_step_result(
                pipeline_run_id=pipeline_run_id,
                step_id=step["id"],
                step_order=step_order,
                status="failed",
                error_message=str(e),
            )
            all_successful = False
            break

    # Update final pipeline status
    final_status = "completed" if all_successful else "failed"
    update_pipeline_status(pipeline_run_id, final_status)

    # Update submission status
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    client.table("submissions").update({"status": final_status}).eq(
        "id", submission_id
    ).execute()

    return {
        "pipeline_run_id": pipeline_run_id,
        "status": final_status,
        "steps_executed": len(recipe_steps) if all_successful else step_order,
    }
