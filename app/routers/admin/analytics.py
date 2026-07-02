from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func
from typing import List
from pydantic import BaseModel

from ...database import get_session
from ...auth import get_current_admin
from ...models import Student, Job, Application, Offer, Company, User
from ...enums import Branch, OfferStatus
from ...logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


class PlacementMetrics(BaseModel):
    total_students: int
    placed_students: int
    placement_rate: float
    average_ctc: float
    highest_ctc: float
    lowest_ctc: float
    total_offers: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_students": 482,
                "placed_students": 371,
                "placement_rate": 76.97,
                "average_ctc": 18.5,
                "highest_ctc": 45.0,
                "lowest_ctc": 5.0,
                "total_offers": 402
            }
        }


class BranchMetrics(BaseModel):
    branch: str
    total_students: int
    placed_students: int
    placement_rate: float
    average_ctc: float


class CompanyMetrics(BaseModel):
    company_name: str
    offers_made: int
    offers_accepted: int
    average_ctc: float
    total_applications: int


@router.get("/summary", response_model=PlacementMetrics)
def get_placement_summary(
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    
    try:
        total_students = session.exec(
            select(func.count(Student.id)).where(Student.is_active == True)
        ).first() or 0
        
        placed = session.exec(
            select(func.count(func.distinct(Offer.student_id)))
            .where(Offer.status == OfferStatus.accepted)
        ).first() or 0
        
        placement_rate = (placed / total_students * 100) if total_students > 0 else 0
        
        ctc_stats = session.exec(
            select(
                func.avg(Offer.ctc),
                func.max(Offer.ctc),
                func.min(Offer.ctc)
            )
            .where(
                Offer.status == OfferStatus.accepted,
                Offer.ctc.isnot(None)
            )
        ).first()
        
        avg_ctc, max_ctc, min_ctc = ctc_stats or (0, 0, 0)
        
        total_offers = session.exec(
            select(func.count(Offer.id))
            .where(Offer.status == OfferStatus.accepted)
        ).first() or 0
        
        logger.info(f"Analytics summary: {placed}/{total_students} placed at {placement_rate:.1f}%")
        
        return PlacementMetrics(
            total_students=int(total_students),
            placed_students=int(placed),
            placement_rate=round(placement_rate, 2),
            average_ctc=float(avg_ctc or 0),
            highest_ctc=float(max_ctc or 0),
            lowest_ctc=float(min_ctc or 0),
            total_offers=int(total_offers)
        )
    except Exception as e:
        logger.error(f"Error fetching placement summary: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


@router.get("/by-branch", response_model=List[BranchMetrics])
def get_metrics_by_branch(
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    
    try:
        metrics = []
        
        for branch in Branch:
            total = session.exec(
                select(func.count(Student.id))
                .where(
                    (Student.branch == branch) &
                    (Student.is_active == True)
                )
            ).first() or 0
            
            placed = session.exec(
                select(func.count(func.distinct(Offer.student_id)))
                .join(Student, Offer.student_id == Student.id)
                .where(
                    (Offer.status == OfferStatus.accepted) &
                    (Student.branch == branch)
                )
            ).first() or 0
            
            avg_ctc = session.exec(
                select(func.avg(Offer.ctc))
                .join(Student, Offer.student_id == Student.id)
                .where(
                    (Offer.status == OfferStatus.accepted) &
                    (Student.branch == branch) &
                    (Offer.ctc.isnot(None))
                )
            ).first() or 0
            
            rate = (placed / total * 100) if total > 0 else 0
            
            metrics.append(BranchMetrics(
                branch=branch.value,
                total_students=int(total),
                placed_students=int(placed),
                placement_rate=round(rate, 2),
                average_ctc=float(avg_ctc or 0)
            ))
        
        logger.info(f"Generated branch-wise analytics for {len(metrics)} branches")
        return sorted(metrics, key=lambda x: x.placement_rate, reverse=True)
        
    except Exception as e:
        logger.error(f"Error fetching branch metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch branch analytics")


@router.get("/by-company", response_model=List[CompanyMetrics])
def get_metrics_by_company(
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    
    try:
        companies = session.exec(select(Company).where(Company.verified == True)).all()
        
        metrics = []
        
        for company in companies:
            total_offers = session.exec(
                select(func.count(Offer.id))
                .where(Offer.company_id == company.id)
            ).first() or 0
            
            accepted = session.exec(
                select(func.count(Offer.id))
                .where(
                    (Offer.company_id == company.id) &
                    (Offer.status == OfferStatus.accepted)
                )
            ).first() or 0
            
            avg_ctc = session.exec(
                select(func.avg(Offer.ctc))
                .where(
                    (Offer.company_id == company.id) &
                    (Offer.status == OfferStatus.accepted) &
                    (Offer.ctc.isnot(None))
                )
            ).first() or 0
            
            total_apps = session.exec(
                select(func.count(Application.id))
                .join(Job, Application.job_id == Job.id)
                .where(Job.company_id == company.id)
            ).first() or 0
            
            metrics.append(CompanyMetrics(
                company_name=company.name,
                offers_made=int(total_offers),
                offers_accepted=int(accepted),
                average_ctc=float(avg_ctc or 0),
                total_applications=int(total_apps)
            ))
        
        logger.info(f"Generated company-wise analytics for {len(metrics)} companies")
        return sorted(metrics, key=lambda x: x.offers_accepted, reverse=True)
        
    except Exception as e:
        logger.error(f"Error fetching company metrics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch company analytics")
