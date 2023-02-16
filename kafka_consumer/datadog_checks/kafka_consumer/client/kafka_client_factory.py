from datadog_checks.kafka_consumer.client.kafka_client import KafkaClient
from datadog_checks.kafka_consumer.client.kafka_python_client import KafkaPythonClient


def make_client(check, config, tls_context) -> KafkaClient:
    return KafkaPythonClient(check, config, tls_context)
