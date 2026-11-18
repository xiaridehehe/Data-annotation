export type AnnotationRecommendation = {
  plane: "SAG" | "COR" | "AX";
  planeLabel: "矢状位" | "冠状位" | "横断位";
  weighting: "PD-FS" | "T2-FS";
};

function words(value: unknown) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function includesWord(text: string, word: string) {
  return (` ${text} `).includes(` ${word} `);
}

export function annotationRecommendation(series: {
  orientation?: unknown;
  description?: unknown;
}): AnnotationRecommendation | null {
  const orientation = words(series.orientation),
    description = words(series.description),
    compact = description.replace(/\s+/g, ""),
    combined = `${orientation} ${description}`,
    hasFatSuppression =
      includesWord(description, "fs") ||
      compact.includes("fatsat") ||
      compact.includes("fatsuppressed"),
    hasPd = includesWord(description, "pd"),
    hasT2 = includesWord(description, "t2");

  let plane: AnnotationRecommendation["plane"] | null = null;
  if (/\b(sag|sagittal)\b/.test(combined) || /(?:^|o)sag/.test(compact)) plane = "SAG";
  else if (/\b(cor|coronal)\b/.test(combined) || /(?:^|o)cor/.test(compact)) plane = "COR";
  else if (/\b(ax|axial|tra|transverse)\b/.test(combined) || /(?:^|o)ax/.test(compact)) plane = "AX";

  if (!plane || !hasFatSuppression) return null;
  if ((plane === "SAG" || plane === "COR") && hasPd)
    return {
      plane,
      planeLabel: plane === "SAG" ? "矢状位" : "冠状位",
      weighting: "PD-FS",
    };
  if (plane === "AX" && (hasPd || hasT2))
    return {
      plane,
      planeLabel: "横断位",
      weighting: hasPd ? "PD-FS" : "T2-FS",
    };
  return null;
}
