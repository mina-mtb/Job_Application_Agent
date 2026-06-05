import json
import re

class JobMatcher:
    def __init__(self, config: dict, knowledge_manager, llm_provider):
        self.config = config
        self.km = knowledge_manager
        self.llm = llm_provider

    def evaluate_stage1(self, job_data: dict) -> dict:
        """Rule-based filtering."""
        title = job_data.get('title', '').lower()
        desc = job_data.get('description', '').lower()
        location = job_data.get('location', '').lower()

        reject_reasons = []

        # Senior roles requiring 7+ or 8+ years experience
        if 'senior' in title or 'senior' in desc:
            if re.search(r'(7\+?\s*years|8\+?\s*years|10\+?\s*years)', desc):
                reject_reasons.append("Senior role requiring 7+ years experience")

        # Unpaid internship
        if 'unpaid internship' in desc or 'unpaid' in title or 'unpaid' in desc:
            reject_reasons.append("Unpaid internship")

        # Native Swedish only
        if 'native swedish only' in desc or 'native swedish' in desc:
            reject_reasons.append("Native Swedish only")

        loc_config = self.config.get('location_filtering', {})

        # Relocation required
        if loc_config.get('reject_relocation_required', False):
            if 'relocation required' in desc:
                reject_reasons.append("Relocation required")

        # Acceptable locations
        acceptable_locations = [loc.lower() for loc in loc_config.get('preferred_locations', ["göteborg", "gothenburg", "västra götaland"])]
        if loc_config.get('allow_remote', True):
            acceptable_locations.append("remote")
        if loc_config.get('allow_hybrid', True):
            acceptable_locations.append("hybrid")

        is_acceptable_location = False
        for loc in acceptable_locations:
            if loc in location or loc in title or loc in desc:
                is_acceptable_location = True
                break
                
        if not is_acceptable_location:
            reject_reasons.append("Location not in accepted list (Gothenburg/Remote/Hybrid)")

        if reject_reasons:
            return {
                "suitability_score": 0,
                "suitability_category": "Rejected",
                "reasons_for_match": [],
                "weaknesses_or_risks": reject_reasons,
                "status": "not_suitable"
            }

        return {
            "suitability_score": None, 
            "suitability_category": "Pending",
            "reasons_for_match": ["Passed Stage 1 filters"],
            "weaknesses_or_risks": [],
            "status": "stage1_passed"
        }

    def evaluate_stage2(self, job_data: dict) -> dict:
        """AI-based scoring with RAG context."""
        title = job_data.get('title', '')
        desc = job_data.get('description', '')

        query = f"Job title: {title}. Description: {desc}"
        rag_results = self.km.query_knowledge_base(query, top_k=3)
        context = "\n".join([r['text'] for r in rag_results])

        prompt = f"""Evaluate this job against the candidate profile and return a score.
        Job Title: {title}
        Job Description: {desc}
        Candidate Profile Context: {context}

        Return a JSON with:
        suitability_score (0-100),
        suitability_category (High/Medium/Low),
        reasons_for_match (list of strings),
        weaknesses_or_risks (list of strings)
        """

        response = self.llm.generate_completion(prompt)
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
            else:
                result = json.loads(response)
                
            return {
                "suitability_score": result.get("suitability_score", 0),
                "suitability_category": result.get("suitability_category", "Unknown"),
                "reasons_for_match": result.get("reasons_for_match", []),
                "weaknesses_or_risks": result.get("weaknesses_or_risks", []),
                "status": "needs_review"
            }
        except Exception:
            return {
                "suitability_score": 0,
                "suitability_category": "Error",
                "reasons_for_match": [],
                "weaknesses_or_risks": ["Failed to parse AI response"],
                "status": "error"
            }
