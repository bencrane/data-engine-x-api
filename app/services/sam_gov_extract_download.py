# app/services/sam_gov_extract_download.py — SAM.gov extract file download service

from __future__ import annotations

import logging
import os
import zipfile
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SAM_GOV_EXTRACTS_API_URL = "https://api.sam.gov/data-services/v1/extracts"


def download_sam_gov_extract(
    *,
    extract_type: str,
    date: str,
    output_dir: str,
) -> dict[str, Any]:
    """Download a SAM.gov entity extract file from the Extracts API.

    Args:
        extract_type: MONTHLY or DAILY.
        date: Target date in MM/DD/YYYY format (SAM.gov API format).
        output_dir: Directory to write the unzipped .dat file.

    Returns:
        Dict with download_url, zip_path, dat_file_path, source_filename, file_size_bytes.
    """
    settings = get_settings()
    api_key = settings.sam_gov_api_key

    # Step 1: Query the Extracts API for the download URL
    params = {
        "api_key": api_key,
        "fileType": "ENTITY",
        "sensitivity": "PUBLIC",
        "frequency": extract_type,
        "date": date,
    }

    logger.info(
        "sam_gov_extract_api_call",
        extra={
            "extract_type": extract_type,
            "date": date,
            "url": SAM_GOV_EXTRACTS_API_URL,
        },
    )

    response = httpx.get(
        SAM_GOV_EXTRACTS_API_URL,
        params=params,
        timeout=60.0,
    )

    if response.status_code == 429:
        raise RuntimeError(
            f"SAM.gov API rate limit exceeded (429). Only 10 requests/day allowed. "
            f"Response: {response.text[:500]}"
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"SAM.gov Extracts API returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    api_response = response.json()

    # Extract download URL from response
    # The API returns a JSON object with download links
    download_url = None
    if isinstance(api_response, dict):
        # Try common response shapes
        download_url = api_response.get("downloadUrl") or api_response.get("url")
        if not download_url and "links" in api_response:
            links = api_response["links"]
            if isinstance(links, list) and links:
                download_url = links[0].get("href") or links[0].get("url")

    if not download_url:
        raise RuntimeError(
            f"Could not extract download URL from SAM.gov API response: "
            f"{str(api_response)[:500]}"
        )

    # Step 2: Download the ZIP file (stream to disk for large files)
    zip_filename = f"sam_gov_{extract_type.lower()}_{date.replace('/', '-')}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    logger.info(
        "sam_gov_extract_downloading",
        extra={"download_url": download_url, "zip_path": zip_path},
    )

    with httpx.stream("GET", download_url, timeout=600.0) as stream:
        stream.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in stream.iter_bytes(chunk_size=8192):
                f.write(chunk)

    # Step 3: Extract the .dat file from the ZIP
    dat_file_path = None
    source_filename = None

    with zipfile.ZipFile(zip_path, "r") as zf:
        dat_files = [name for name in zf.namelist() if name.lower().endswith(".dat")]
        if not dat_files:
            raise RuntimeError(
                f"No .dat file found in ZIP archive: {zf.namelist()}"
            )

        source_filename = dat_files[0]
        dat_file_path = os.path.join(output_dir, source_filename)
        zf.extract(source_filename, output_dir)

    file_size_bytes = os.path.getsize(dat_file_path)

    logger.info(
        "sam_gov_extract_downloaded",
        extra={
            "dat_file_path": dat_file_path,
            "source_filename": source_filename,
            "file_size_bytes": file_size_bytes,
        },
    )

    return {
        "download_url": download_url,
        "zip_path": zip_path,
        "dat_file_path": dat_file_path,
        "source_filename": source_filename,
        "file_size_bytes": file_size_bytes,
    }
