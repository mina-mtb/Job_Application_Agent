from core.cv_tailor import CVTailor
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager

class MockLLM:
    def generate_completion(self, prompt):
        return '{"evaluation": "test", "chosen_structure": "A", "profile": "prof", "skills": "sk"}'

db = DBManager()
km = KnowledgeManager()
llm = MockLLM()
tailor = CVTailor(db, km, llm, {})

try:
    tailor.generate_tailored_cv('manual_4048bced')
    print('SUCCESS in script!')
except Exception as e:
    import traceback
    traceback.print_exc()
