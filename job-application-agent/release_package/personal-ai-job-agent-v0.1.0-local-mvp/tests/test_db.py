def test_insert_and_get_job(test_db):
    job_data = {
        "job_id": "1",
        "title": "Software Engineer",
        "company": "Test Co",
        "location": "Remote",
        "job_link": "http://test.com/1",
        "description": "Test description"
    }
    inserted = test_db.insert_job(job_data)
    assert inserted is True

    fetched = test_db.get_job_by_link("http://test.com/1")
    assert fetched is not None
    assert fetched["title"] == "Software Engineer"
    assert fetched["status"] == "new"

def test_duplicate_job_ignored(test_db):
    job_data = {
        "job_id": "1",
        "title": "Software Engineer",
        "job_link": "http://test.com/1",
    }
    test_db.insert_job(job_data)
    
    # Insert duplicate link
    dup_job_data = {
        "job_id": "2",
        "title": "Different Title",
        "job_link": "http://test.com/1",
    }
    inserted = test_db.insert_job(dup_job_data)
    assert inserted is False
    
    # Verify original is kept
    fetched = test_db.get_job_by_link("http://test.com/1")
    assert fetched["job_id"] == "1"
    assert fetched["title"] == "Software Engineer"

def test_status_preserved_on_duplicate(test_db):
    job_data = {
        "job_id": "1",
        "title": "SE",
        "job_link": "http://test.com/1",
    }
    test_db.insert_job(job_data)
    
    # Manually update status
    test_db.execute_query("UPDATE jobs SET status = 'applied' WHERE job_link = 'http://test.com/1'")
    
    # Try insert duplicate
    test_db.insert_job(job_data)
    
    fetched = test_db.get_job_by_link("http://test.com/1")
    assert fetched["status"] == "applied"
