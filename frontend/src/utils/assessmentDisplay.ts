export const assessmentGradeLabel = (grade: string) => {
  const demoGrade = /^DEMO_GRADE_([A-Z0-9]+)$/.exec(grade)
  return demoGrade ? `평가 구간 ${demoGrade[1]}` : grade
}

export const assessmentGradeSetLabel = (grades: string[]) => grades.map(assessmentGradeLabel).join(' · ')
