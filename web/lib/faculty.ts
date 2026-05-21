export interface Course {
  subject_code: string;
  subject_name: string;
  course_code: string;
  course_name: string;
}

export interface FacultyRecord {
  id: string;
  name: string;
  title: string;
  email: string;
  email_inferred: boolean;
  phone: string;
  office: string;
  departments: string[];
  bio: string;
  photo_url: string;
  faculty_page_url: string;
  courses_taught: Course[];
  source: string[];
}

export interface SourceResult extends FacultyRecord {
  relevance_note: string;
}
