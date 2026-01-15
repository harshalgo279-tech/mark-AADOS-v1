# backend/app/models/__init__.py
from app.models.lead import Lead
from app.models.data_packet import DataPacket
from app.models.call import Call
from app.models.email import Email
from app.models.linkedin import LinkedInMessage

__all__ = ['Lead', 'DataPacket', 'Call', 'Email', 'LinkedInMessage']
