from .client import NtustClient

QUERY_BASE_URL = "https://querycourse.ntust.edu.tw/QueryCourse/api/"

class CourseQueryClient(NtustClient):
    def __init__(self):
        super().__init__()

    def get_semesters(self):
        """Fetches the list of semesters."""
        try:
            url = QUERY_BASE_URL + "semestersinfo"
            resp = self.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"Error fetching semesters: {e}")
        return []

    def get_latest_semester(self):
        """Returns the latest regular semester code (ending in 1 or 2, skipping summer H sessions)."""
        semesters = self.get_semesters()
        for sem in semesters:
            code = sem.get('Semester', '')
            if code and code[-1] in ('1', '2'):
                return code
        if semesters:
            return semesters[0].get('Semester')
        return "1151" # Fallback

    def search_courses(self, semester=None, course_no=None, course_name=None, teacher=None, language="zh", old_course=False):
        """
        Searches for courses. If semester is None, uses the latest active semester.
        """
        if semester is None:
            semester = self.get_latest_semester()
            
        url = QUERY_BASE_URL + "courses"
        payload = {
            "semester": semester,
            "courseNo": course_no if course_no else "",
            "courseName": course_name if course_name else "",
            "courseTeacher": teacher if teacher else "",
            "dimension": "",
            "courseNotes": "",
            "foreignLanguage": 0,
            "onlyGeneral": 0,
            "OnlyNTUST": 0,
            "onlyMaster": 0,
            "onlyUnderGraduate": 0,
            "onlyNode": 0,
            "language": language
        }
        resp = self.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def search_archived_info(self, course_no="", course_name="", dept=""):
        """
        Searches the 'ArchivedTitleAndOutline' endpoint. 
        Note: This is useful for getting basic info of courses not in current schedule.
        """
        url = QUERY_BASE_URL + "ArchivedTitleAndOutline"
        params = {
            "DeptNo": dept if dept else "",
            "CourseName": course_name if course_name else "",
            "EngName": "",
            "CourseNo": course_no if course_no else ""
        }
        try:
            resp = self.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error searching archived: {e}")
            return []
