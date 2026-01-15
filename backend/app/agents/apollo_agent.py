import httpx
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.lead import Lead
from app.config import settings
from app.utils.logger import logger


class ApolloAgent:
    """
    Agent responsible for fetching leads from Apollo API
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.api_key = settings.APOLLO_API_KEY
        self.base_url = "https://api.apollo.io/v1"
    
    async def fetch_leads(
        self,
        job_titles: List[str] = None,
        industries: List[str] = None,
        company_sizes: List[str] = None,
        locations: List[str] = None,
        limit: int = 50
    ):
        """
        Fetch leads from Apollo API and store in database
        """
        try:
            logger.info(f"Fetching up to {limit} leads from Apollo...")
            
            # Get leads from Apollo
            if self.api_key:
                apollo_leads = await self._fetch_from_apollo_api(
                    job_titles, industries, company_sizes, locations, limit
                )
            else:
                logger.warning("Apollo API key not configured, using mock data")
                apollo_leads = self._generate_mock_leads(limit)
            
            # Store leads in database
            new_leads = []
            duplicates = 0
            
            for apollo_lead in apollo_leads:
                # Check for duplicates
                existing = self.db.query(Lead).filter(
                    Lead.email == apollo_lead.get("email")
                ).first()
                
                if existing:
                    duplicates += 1
                    logger.debug(f"Duplicate lead: {apollo_lead.get('email')}")
                    continue
                
                # Create new lead
                lead = Lead(
                    apollo_id=apollo_lead.get("id"),
                    name=apollo_lead.get("name"),
                    email=apollo_lead.get("email"),
                    phone=apollo_lead.get("phone"),
                    company=apollo_lead.get("company"),
                    title=apollo_lead.get("title"),
                    seniority=apollo_lead.get("seniority"),
                    linkedin_url=apollo_lead.get("linkedin_url"),
                    company_size=apollo_lead.get("company_size"),
                    company_industry=apollo_lead.get("industry"),
                    company_location=apollo_lead.get("location"),
                    company_website=apollo_lead.get("website"),
                    company_description=apollo_lead.get("company_description"),
                    status="new",
                    created_at=datetime.utcnow()
                )
                
                self.db.add(lead)
                new_leads.append(lead)
            
            self.db.commit()
            
            logger.info(f"Successfully fetched {len(new_leads)} new leads, {duplicates} duplicates skipped")
            
            return new_leads
            
        except Exception as e:
            logger.error(f"Error fetching leads from Apollo: {str(e)}")
            self.db.rollback()
            raise
    
    async def _fetch_from_apollo_api(
        self,
        job_titles: List[str],
        industries: List[str],
        company_sizes: List[str],
        locations: List[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Real Apollo API call
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/mixed_people/search",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache"
                    },
                    json={
                        "api_key": self.api_key,
                        "q_organization_job_titles": job_titles or ["CTO", "VP Engineering", "Director"],
                        "organization_industry_tag_ids": industries or [],
                        "organization_num_employees_ranges": company_sizes or ["51-200", "201-500", "501-1000"],
                        "organization_locations": locations or ["United States"],
                        "page": 1,
                        "per_page": limit
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_apollo_response(data)
                else:
                    logger.error(f"Apollo API error: {response.status_code} - {response.text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Apollo API request failed: {str(e)}")
            return []
    
    def _parse_apollo_response(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse Apollo API response"""
        leads = []
        
        for person in data.get("people", []):
            org = person.get("organization", {})
            
            leads.append({
                "id": person.get("id"),
                "name": person.get("name"),
                "email": person.get("email"),
                "phone": person.get("phone_numbers", [{}])[0].get("raw_number") if person.get("phone_numbers") else None,
                "company": org.get("name"),
                "title": person.get("title"),
                "seniority": person.get("seniority"),
                "linkedin_url": person.get("linkedin_url"),
                "company_size": org.get("estimated_num_employees"),
                "industry": org.get("industry"),
                "location": f"{person.get('city', '')}, {person.get('state', '')}, {person.get('country', '')}".strip(", "),
                "website": org.get("website_url"),
                "company_description": org.get("short_description", "")
            })
        
        return leads
    
    def _generate_mock_leads(self, count: int) -> List[Dict[str, Any]]:
        """Generate mock leads for testing"""
        companies = [
            {"name": "TechVision Inc", "industry": "Technology", "size": "201-500", "desc": "Enterprise software solutions"},
            {"name": "DataFlow Systems", "industry": "SaaS", "size": "51-200", "desc": "Cloud data analytics platform"},
            {"name": "CloudScale Corp", "industry": "Cloud Services", "size": "501-1000", "desc": "Cloud infrastructure provider"},
            {"name": "AIFirst Solutions", "industry": "Artificial Intelligence", "size": "101-200", "desc": "AI consulting and implementation"},
            {"name": "RetailTech Pro", "industry": "E-commerce", "size": "201-500", "desc": "E-commerce platform and tools"}
        ]
        
        titles = [
            {"title": "Chief Technology Officer", "seniority": "C-Level"},
            {"title": "VP of Engineering", "seniority": "VP"},
            {"title": "Director of Operations", "seniority": "Director"},
            {"title": "Head of Product", "seniority": "VP"},
            {"title": "VP of Sales", "seniority": "VP"}
        ]
        
        leads = []
        for i in range(min(count, 50)):
            company = companies[i % len(companies)]
            title_info = titles[i % len(titles)]
            
            leads.append({
                "id": f"apollo_mock_{i}",
                "name": f"John Doe {i}",
                "email": f"johndoe{i}@{company['name'].lower().replace(' ', '')}.com",
                "phone": f"+1555{i:04d}0000",
                "company": company["name"],
                "title": title_info["title"],
                "seniority": title_info["seniority"],
                "linkedin_url": f"https://linkedin.com/in/johndoe{i}",
                "company_size": company["size"],
                "industry": company["industry"],
                "location": "San Francisco, CA, United States",
                "website": f"https://www.{company['name'].lower().replace(' ', '')}.com",
                "company_description": company["desc"]
            })
        
        return leads