import sqlite3
import os
import shutil

conn = sqlite3.connect('database/jobs.db')
c = conn.cursor()
c.execute("UPDATE jobs SET status = 'needs_review', generated_cv_path = NULL WHERE status = 'cv_generated'")
conn.commit()
conn.close()

if os.path.exists('outputs'):
    shutil.rmtree('outputs')

print('DB reset done')
