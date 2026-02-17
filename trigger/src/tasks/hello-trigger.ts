import { logger, task } from "@trigger.dev/sdk/v3";

interface HelloTriggerPayload {
  name?: string;
}

export const helloTrigger = task({
  id: "hello-trigger",
  run: async (payload: HelloTriggerPayload) => {
    const name = payload.name?.trim() || "world";
    const message = `Hello, ${name}!`;

    logger.info("hello-trigger executed", { name, message });

    return {
      ok: true,
      message,
      timestamp: new Date().toISOString(),
    };
  },
});
