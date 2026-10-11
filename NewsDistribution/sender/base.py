"""Shared types for the message sender (piece 9).

Mirrors the design in Report 2: ChannelAdapter, Message and SendResult.
The Telegram and email adapters should subclass ChannelAdapter too, so the
dispatcher / retry code can treat every channel the same way.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    """A story formatted for one channel."""
    text: str
    link: str
    subject: Optional[str] = None  # email only


@dataclass
class SendResult:
    """Outcome of one send attempt."""
    ok: bool
    permanent: bool = False             # True if retrying cannot help
    error: Optional[str] = None
    retry_after: Optional[float] = None  # seconds the channel asked us to wait


class ChannelAdapter(ABC):
    @abstractmethod
    def validate_contact(self, contact: str) -> bool: ...

    @abstractmethod
    def format_message(self, item) -> Message: ...

    @abstractmethod
    def send(self, contact: str, message: Message) -> SendResult: ...

    @abstractmethod
    def send_test(self, contact: str, code: str) -> SendResult: ...
