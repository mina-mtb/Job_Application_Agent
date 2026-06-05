from llm.base_provider import BaseProvider

class MockProvider(BaseProvider):
    def __init__(self, model_name="mock-model"):
        self.model_name = model_name

    def generate_completion(self, prompt: str, system_prompt: str = "") -> str:
        """Returns mock responses for testing without spending tokens."""
        if "score" in prompt.lower() or "evaluate" in prompt.lower():
            return '{"suitability_score": 85, "suitability_category": "High", "reasons_for_match": ["Strong match for requirements"], "weaknesses_or_risks": ["Limited evidence for some requirements"]}'
        elif "profile" in prompt.lower() or "skills" in prompt.lower():
            import json
            evidence_snippets = []
            for line in prompt.split('\n'):
                if 'Source:' in line:
                    evidence_snippets.append(line.split('-', 1)[-1].strip()[:50])
            
            if evidence_snippets:
                profile = "Software Developer with a background in .NET backend development, cloud technologies, and current studies in AI/ML. Experienced in C#, ASP.NET Core, REST APIs, microservices, and Power Platform, with additional exposure to RAG, LLM-powered services, and machine learning through academic and project-based work."
                skills = [
                    "C#, .NET / ASP.NET Core, REST APIs",
                    "SQL Server, Entity Framework, Dataverse",
                    "Azure, AWS, Docker, Kubernetes",
                    "Power Apps, Power Automate, Power BI",
                    "Python, RAG, LLM-powered services, Machine Learning"
                ]
            else:
                profile = "Experienced Backend and AI Engineer."
                skills = ["Software Engineering", "Machine Learning"]
                
            return json.dumps({"profile": profile, "skills": skills})
        return "Mock response"
