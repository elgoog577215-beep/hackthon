// Route-owned I/O scope, not a second course or learning store.
let courseId = ''
export const setTeacherPreviewCourse = (value: string): void => { courseId = value }
export const isTeacherPreviewCourse = (value?: string): boolean => Boolean(courseId && (!value || value === courseId))
