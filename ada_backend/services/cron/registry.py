from ada_backend.database.models import CronEntrypoint
from ada_backend.services.cron.core import CronEntrySpec
from ada_backend.services.cron.entries.agent_inference import spec as agent_inference_spec
from ada_backend.services.cron.entries.dummy_print import spec as dummy_print_spec
from ada_backend.services.cron.entries.endpoint_polling import spec as endpoint_polling_spec

CRON_REGISTRY: dict[CronEntrypoint, CronEntrySpec] = {
    CronEntrypoint.AGENT_INFERENCE: agent_inference_spec,
    CronEntrypoint.DUMMY_PRINT: dummy_print_spec,
    CronEntrypoint.ENDPOINT_POLLING: endpoint_polling_spec,
}
