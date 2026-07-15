import random
from abc import ABC, abstractmethod

from app.models.enums import Channel

# Provider error
class ProviderError(Exception):
    """Raised when a mocked provider fails to deliver a message."""

# Notification provider
class NotificationProvider(ABC):
    channel: Channel

    @abstractmethod
    def send(self, *, user_id: str, subject: str | None, body: str) -> str:
        """Send the message. Returns a provider message id on success, raises ProviderError on failure."""

# Mock email provider
class MockEmailProvider(NotificationProvider):
    channel = Channel.EMAIL

    def send(self, *, user_id: str, subject: str | None, body: str) -> str:
        if random.random() < 0.1:
            raise ProviderError("Simulated email provider failure")
        return f"email-{random.randint(100000, 999999)}"

# Mock SMS provider
class MockSmsProvider(NotificationProvider):
    channel = Channel.SMS

    def send(self, *, user_id: str, subject: str | None, body: str) -> str:
        if len(body) > 1600:
            raise ProviderError("SMS body exceeds max length")
        if random.random() < 0.1:
            raise ProviderError("Simulated SMS provider failure")
        return f"sms-{random.randint(100000, 999999)}"

# Mock push provider
class MockPushProvider(NotificationProvider):
    channel = Channel.PUSH

    def send(self, *, user_id: str, subject: str | None, body: str) -> str:
        if random.random() < 0.1:
            raise ProviderError("Simulated push provider failure")
        return f"push-{random.randint(100000, 999999)}"

# Providers map
_PROVIDERS: dict[Channel, NotificationProvider] = {
    Channel.EMAIL: MockEmailProvider(),
    Channel.SMS: MockSmsProvider(),
    Channel.PUSH: MockPushProvider(),
}

# Get the provider for a given channel
def get_provider(channel: Channel) -> NotificationProvider:
    return _PROVIDERS[channel]
