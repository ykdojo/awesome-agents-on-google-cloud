# Situation 7: prototype to production

No Python file here; this situation is tooling and configuration.

- **Evaluation**: chat with your agent in the dev UI (`adk web`), save the session as an evalset from the Eval tab, then replay it in CI:

  ```bash
  pip install "google-adk[eval]"
  adk eval path/to/agent path/to/evalset.evalset.json
  ```

  Docs: https://adk.dev/evaluate/

- **Observability**: ADK emits OpenTelemetry traces for every agent, tool, and model step.

  ```bash
  export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://your-collector:4318/v1/traces"
  adk web path/to/agents   # or: adk web --otel_to_cloud for Cloud Trace
  ```

  Docs: https://adk.dev/observability/traces/

- **Resilience**: retries with model feedback (https://adk.dev/integrations/reflect-and-retry/) and resumable invocations (https://adk.dev/runtime/resume/) are App-level config:

  ```python
  app = App(name="my_app", root_agent=root_agent,
            plugins=[ReflectAndRetryToolPlugin(max_retries=3)],
            resumability_config=ResumabilityConfig(is_resumable=True))
  ```
