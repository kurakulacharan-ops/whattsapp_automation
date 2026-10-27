"""
Schemas matching the ACTUAL Interakt webhook payload — verified against a
real captured message_received event on 16 Sep 2026 (image + caption).

Do not "clean up" field names to look nicer — these match Interakt's wire
format exactly so incoming JSON parses without guesswork.
"""
from typing import Optional
from pydantic import BaseModel


class CustomerTraits(BaseModel):
    name: Optional[str] = None  # WhatsApp display name — NOT the caption name, don't confuse these


class Customer(BaseModel):
    id: str
    channel_phone_number: str  # e.g. "919123360859" — THE roster lookup key
    phone_number: str
    country_code: str
    traits: CustomerTraits


class MessageData(BaseModel):
    id: str
    chat_message_type: str
    message_status: str
    received_at_utc: str
    message_content_type: str          # "Text" | "Image" (confirmed values)
    media_url: Optional[str] = None    # populated when message_content_type == "Image"
    message: Optional[str] = None      # holds BOTH plain text AND image captions — same field
    meta_data: dict = {}


class WebhookData(BaseModel):
    customer: Customer
    message: MessageData
    channel_type: str
    organization_id: str
    whatsapp_api_number: str


class InteraktWebhookPayload(BaseModel):
    version: str
    timestamp: str
    type: str  # "message_received" is the one we act on
    data: WebhookData
