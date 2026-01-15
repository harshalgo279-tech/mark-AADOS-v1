# backend/app/services/apollo_service.py
import httpx
from typing import List, Dict, Any
from app.config import settings
from app.utils.logger import logger


class ApolloService:
    """Service for interacting with Apollo API"""
    
    def __init__(self):
        self.api_key = settings.APOLLO_API_KEY
        self.base_url = "https://api.apollo.io/v1"
    
    async def search_people(
        self,
        job_titles: List[str] = None,
        industries: List[str] = None,
        company_sizes: List[str] = None,
        locations: List[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search for people in Apollo"""
        
        if not self.api_key:
            logger.warning("Apollo API key not configured, returning mock data")
            return self._generate_mock_leads(limit)
        
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
                        "q_organization_job_titles": job_titles or ["CTO", "VP Engineering"],
                        "organization_industry_tag_ids": industries or [],
                        "organization_num_employees_ranges": company_sizes or ["51-200", "201-500"],
                        "organization_locations": locations or ["United States"],
                        "page": 1,
                        "per_page": limit
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_response(data)
                else:
                    logger.error(f"Apollo API error: {response.status_code}")
                    return self._generate_mock_leads(limit)
                    
        except Exception as e:
            logger.error(f"Apollo API request failed: {str(e)}")
            return self._generate_mock_leads(limit)
    
    def _parse_response(self, data: Dict) -> List[Dict[str, Any]]:
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
            {"name": "TechVision Inc", "industry": "Technology", "size": "201-500", "desc": "Enterprise software solutions for modern businesses"},
            {"name": "DataFlow Systems", "industry": "SaaS", "size": "51-200", "desc": "Cloud-based data analytics platform"},
            {"name": "CloudScale Corp", "industry": "Cloud Services", "size": "501-1000", "desc": "Scalable cloud infrastructure provider"},
            {"name": "AIFirst Solutions", "industry": "Artificial Intelligence", "size": "101-200", "desc": "AI consulting and implementation services"},
            {"name": "RetailTech Pro", "industry": "E-commerce", "size": "201-500", "desc": "E-commerce platform and retail solutions"},
            {"name": "FinanceFlow", "industry": "FinTech", "size": "301-500", "desc": "Financial technology and payment solutions"},
            {"name": "HealthSync", "industry": "Healthcare Technology", "size": "151-300", "desc": "Healthcare management software"},
            {"name": "EduTech Global", "industry": "Education Technology", "size": "101-250", "desc": "Online learning platforms and tools"}
        ]
        
        titles = [
            {"title": "Chief Technology Officer", "seniority": "C-Level"},
            {"title": "VP of Engineering", "seniority": "VP"},
            {"title": "Director of Operations", "seniority": "Director"},
            {"title": "Head of Product", "seniority": "VP"},
            {"title": "VP of Sales", "seniority": "VP"},
            {"title": "Director of Business Development", "seniority": "Director"},
            {"title": "Chief Operating Officer", "seniority": "C-Level"}
        ]
        
        first_names = ["John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa", "James", "Maria"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
        
        leads = []
        for i in range(min(count, 100)):
            company = companies[i % len(companies)]
            title_info = titles[i % len(titles)]
            first_name = first_names[i % len(first_names)]
            last_name = last_names[i % len(last_names)]
            full_name = f"{first_name} {last_name}"
            
            leads.append({
                "id": f"apollo_mock_{i}",
                "name": full_name,
                "email": f"{first_name.lower()}.{last_name.lower()}{i}@{company['name'].lower().replace(' ', '')}.com",
                "phone": f"+1555{i:04d}0000",
                "company": company["name"],
                "title": title_info["title"],
                "seniority": title_info["seniority"],
                "linkedin_url": f"https://linkedin.com/in/{first_name.lower()}{last_name.lower()}{i}",
                "company_size": company["size"],
                "industry": company["industry"],
                "location": "San Francisco, CA, United States",
                "website": f"https://www.{company['name'].lower().replace(' ', '')}.com",
                "company_description": company["desc"]
            })
        
        return leads