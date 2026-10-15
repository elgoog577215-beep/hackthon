import { teachingDiagramCatalog } from '../src/utils/teaching-diagrams';

// Public, hand-authored layout fixtures; these never read or update a course.
export const teachingDiagramLayoutSamples = ['zh', 'en'].map(locale => {
  const en = locale === 'en';
  return {
    id: `flow-layout-${locale}`,
    schema_version: teachingDiagramCatalog.schema_version,
    type: 'flowchart',
    title: en ? 'Merge, branch and formula layout' : '合流、分支与公式排版',
    summary: en ? 'Hand-authored layout example; labels and formulas stay complete.' : '自编排版示例，检查合流、分支、连线和公式的完整显示。',
    source: en ? 'Public hypothetical example' : '自编假设示例',
    nodes: [
      { id: 'gap', label: en ? 'Air gap thickness h' : '空气隙厚度 h' },
      { id: 'phase', label: en ? 'Half-wave loss λ/2' : '半波损失 λ/2' },
      { id: 'path', label: en ? 'Geometric path difference 2h' : '几何路径差 2h' },
      { id: 'total', label: en ? 'Total optical path difference δ' : '总光程差 δ' },
      { id: 'bright', label: en ? 'Bright: δ=(k+1)λ' : '亮纹：δ=(k+1)λ' },
      { id: 'dark', label: en ? 'Dark: δ=(k+1/2)λ' : '暗纹：δ=(k+1/2)λ' },
    ],
    edges: [
      { from: 'gap', to: 'path', label: en ? 'Normal incidence' : '垂直入射' },
      { from: 'phase', to: 'path', label: '+' },
      { from: 'path', to: 'total', label: '+' },
      { from: 'total', to: 'bright', label: en ? 'Satisfies' : '满足' },
      { from: 'total', to: 'dark', label: en ? 'Satisfies' : '满足' },
    ],
  };
});
