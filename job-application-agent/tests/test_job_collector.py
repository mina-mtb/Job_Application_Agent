from core.job_collector import JobCollector

def test_collect_jobs_mock_apify(test_db):
    collector = JobCollector(test_db)
    result = collector.collect_jobs()
    
    assert result["fetched"] == 3
    assert result["new_inserted"] == 2
    assert result["duplicates_ignored"] == 1
    
    all_jobs = test_db.get_all_jobs()
    assert len(all_jobs) == 2
    
    titles = [job["title"] for job in all_jobs]
    assert "Junior .NET Developer" in titles
    assert "AI Engineer" in titles
    assert "AI Engineer (Duplicate)" not in titles
