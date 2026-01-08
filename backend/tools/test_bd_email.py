import asyncio
import time
from app.database import SessionLocal
from app.models.lead import Lead
from app.agents.data_packet_agent import DataPacketAgent
from app.services.bd_notification_service import BDNotificationService


async def main():
    db = SessionLocal()
    try:
        # Create or get a test lead
        test_email = f"bd_test_{int(time.time())}@example.com"
        lead = db.query(Lead).filter(Lead.email == test_email).first()
        if not lead:
            lead = Lead(
                name="BD Test Lead",
                email=test_email,
                phone="+10000000000",
                company="Test Company",
                title="CTO",
                status="cold",
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            print("Created test lead", lead.id, lead.email)
        else:
            print("Using existing test lead", lead.id, lead.email)

        # Generate data packet (idempotent)
        agent = DataPacketAgent(db)
        packet = await agent.create_data_packet(lead)
        print("Data packet id:", getattr(packet, "id", None))

        # Send BD notification
        svc = BDNotificationService(db)
        await svc.send_notification(packet, lead)
        print("BD notification attempted")

    except Exception as e:
        print("Error during BD test:", e)
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
