class ApifyClient:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def fetch_linkedin_jobs(self, query="Software Engineer", location="Gothenburg"):
        """
        Mock implementation returning a static JSON-like structure.
        In Phase 2+, this will call the real Apify API.
        """
        return [
            {
                "id": "job_123",
                "title": "Junior .NET Developer",
                "companyName": "Volvo Cars",
                "location": "Gothenburg",
                "url": "https://linkedin.com/jobs/view/123",
                "description": "We are looking for a C# .NET developer..."
            },
            {
                "id": "job_124",
                "title": "AI Engineer",
                "companyName": "Zenseact",
                "location": "Göteborg",
                "url": "https://linkedin.com/jobs/view/124",
                "description": "Python, ML, PyTorch required."
            },
            {
                # Duplicate link to test DB constraint
                "id": "job_124_dup",
                "title": "AI Engineer (Duplicate)",
                "companyName": "Zenseact",
                "location": "Göteborg",
                "url": "https://linkedin.com/jobs/view/124",
                "description": "Duplicate post."
            }
        ]
