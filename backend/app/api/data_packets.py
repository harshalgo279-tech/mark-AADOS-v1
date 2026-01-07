from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.data_packet import DataPacket
from app.models.lead import Lead
from app.agents.data_packet_agent import DataPacketAgent

router = APIRouter(
    prefix="/api/data-packet",
    tags=["data_packets"]
)


def packet_to_dict(p: DataPacket):
    return {
        "id": p.id,
        "lead_id": p.lead_id,
        "company_analysis": p.company_analysis,
        "pain_points": p.pain_points,
        "use_case_1_title": p.use_case_1_title,
        "use_case_1_description": p.use_case_1_description,
        "use_case_1_impact": p.use_case_1_impact,
        "use_case_2_title": p.use_case_2_title,
        "use_case_2_description": p.use_case_2_description,
        "use_case_2_impact": p.use_case_2_impact,
        "use_case_3_title": p.use_case_3_title,
        "use_case_3_description": p.use_case_3_description,
        "use_case_3_impact": p.use_case_3_impact,
        "solution_1_title": p.solution_1_title,
        "solution_1_description": p.solution_1_description,
        "solution_1_roi": p.solution_1_roi,
        "solution_2_title": p.solution_2_title,
        "solution_2_description": p.solution_2_description,
        "solution_2_roi": p.solution_2_roi,
        "solution_3_title": p.solution_3_title,
        "solution_3_description": p.solution_3_description,
        "solution_3_roi": p.solution_3_roi,
        "confidence_score": p.confidence_score,
        "generated_at": p.generated_at
    }


@router.get("/{lead_id}")
async def get_data_packet(lead_id: int, db: Session = Depends(get_db)):
    packet = db.query(DataPacket).filter(DataPacket.lead_id == lead_id).first()

    if not packet:
        raise HTTPException(status_code=404, detail="Data packet not found")

    return packet_to_dict(packet)


@router.post("/generate/{lead_id}")
async def generate_data_packet(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    agent = DataPacketAgent(db)
    packet = await agent.create_data_packet(lead)

    return packet_to_dict(packet)
