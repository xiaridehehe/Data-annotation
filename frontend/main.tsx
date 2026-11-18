import React, { useState as S, useEffect as E, useRef as R } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import {
  req,
  loadState,
  importLocal,
  imageId,
  exportLocal,
  newId,
  workflowRequest,
  prepareImages,
  localImageAvailability,
  locallyHiddenStudies,
  removeLocalStudyImages,
} from "./local";
import { annotationRecommendation } from "./seriesRecommendation";
let RenderingEngine: any, Enums: any, viewerReady: Promise<void>;
function prepareViewer() {
  return (viewerReady ||= Promise.all([
    import("@cornerstonejs/core"),
    import("@cornerstonejs/dicom-image-loader"),
  ]).then(async ([core, loader]) => {
    RenderingEngine = core.RenderingEngine;
    Enums = core.Enums;
    await core.init();
    loader.init({
      maxWebWorkers: Math.min(
        8,
        Math.max(4, (navigator.hardwareConcurrency || 4) - 1),
      ),
    });
    await prepareImages();
  }));
}
function App({
  user,
  onLogout,
  reviewSubmission = null,
  reviewChanges = null,
  onBack = null,
  onReviewed = null,
}) {
  const readOnlyReview =
    !!reviewSubmission && reviewSubmission.status !== "SUBMITTED";
  let [s, set] = S<any>({
      series: [],
      studies: [],
      patients: [],
      instances: [],
      diseases: [],
      assessments: [],
      lesions: [],
      boxes: [],
    }),
    [sid, series] = S(() => localStorage.getItem("knee-selected-series") || ""),
    [di, disease] = S("ACL_INJURY"),
    [idx, slice] = S(
      () => Number(localStorage.getItem("knee-selected-slice")) || 0,
    ),
    [lid, lesion] = S(""),
    [expanded, expand] = S(""),
    [drawLesion, setDrawLesion] = S(""),
    [target, T] = S(""),
    [tool, mode] = S("select"),
    [status, msg] = S("就绪"),
    [pending, P] = S(0),
    [syncing, SP] = S(0),
    [queued, Q] = S(0),
    [syncError, setSyncError] = S(""),
    [busy, B] = S(false),
    [archive, A] = S(""),
    [issueOpen, IO] = S(false),
    [preview, V] = S<any>(null),
    [clipboard, CB] = S<any>(null),
    [renderVersion, RV] = S(0),
    [localImages, setLocalImages] = S({
      available: 0,
      total: 0,
      checking: true,
    }),
    [imageStatus, imageMsg] = S("请选择序列"),
    [draft, D] = S<any>(null),
    [history, H] = S<any[]>([]),
    [future, F] = S<any[]>([]);
  let lastSelectedBoxes = R<Record<string, string>>({});
  let el = R<HTMLDivElement>(null),
    liveRect = R<SVGRectElement>(null),
    vp = R<any>(null),
    engine = R<any>(null),
    drag = R<any>(null);
  let ser = s.series.find((x) => x.id === sid),
    study = ser?.study_id,
    dis = s.diseases.find((x) => x.id === di),
    images = s.instances
      .filter((x) => x.series_id === sid)
      .sort((a, b) => a.order - b.order),
    im = images[idx],
    ls = s.lesions.filter(
      (x) =>
        x.series_id === sid &&
        x.disease_type_id === di &&
        (di !== "MENISCUS_INJURY" ||
          (x.tissue_type ||
            { 内侧半月板: "MEDIAL_MENISCUS", 外侧半月板: "LATERAL_MENISCUS" }[
              x.attributes_json?.["半月板类型"]
            ]) === target),
    ),
    selected = ls.find((x) => x.id === lid),
    meniscusTarget =
      selected?.attributes_json?.["半月板类型"] === "内侧半月板"
        ? "MEDIAL_MENISCUS"
        : selected?.attributes_json?.["半月板类型"] === "外侧半月板"
          ? "LATERAL_MENISCUS"
          : null,
    ass = s.assessments.find(
      (x) =>
        x.study_id === study &&
        x.series_id === sid &&
        x.disease_type_id === di &&
        (di !== "MENISCUS_INJURY" || x.target_key === target),
    );
  let activeStudyId = reviewSubmission?.study_uid || study,
    displayedStudies = activeStudyId
      ? s.studies.filter((x) => x.id === activeStudyId)
      : s.studies.slice(0, 1),
    selectedStudy = s.studies.find((x) => x.id === activeStudyId),
    selectedPatient = s.patients.find(
      (x) => x.id === selectedStudy?.patient_id,
    ),
    studyImageIds = s.instances
      .filter((instance) =>
        s.series.some(
          (item) =>
            item.id === instance.series_id && item.study_id === activeStudyId,
        ),
      )
      .map((instance) => instance.id),
    patientIdHint =
      selectedPatient?.patient_code ||
      reviewSubmission?.patient_code ||
      reviewSubmission?.patient_id ||
      selectedPatient?.id ||
      "未知 Patient ID";
  let [submissions, setSubmissions] = S<any[]>([]);
  let currentSubmission = submissions.find((item) => item.study_uid === study),
    pendingAnnotatorReview =
      !reviewSubmission &&
      user.role === "ANNOTATOR" &&
      currentSubmission?.status === "SUBMITTED",
    editLocked = readOnlyReview || pendingAnnotatorReview;
  let pendingSaves = R<Set<Promise<any>>>(new Set());
  let debounceSaves = R<Map<string, any>>(new Map());
  let loadedStudy = R("");
  E(() => {
    localStorage.setItem("knee-selected-series", sid);
    localStorage.setItem("knee-selected-slice", String(idx));
  }, [sid, idx]);
  function restrictToReviewStudy(data) {
    if (!reviewSubmission) return data;
    let studyIds = new Set([reviewSubmission.study_uid]);
    data.studies = data.studies.filter((x) => studyIds.has(x.id));
    let patientIds = new Set(data.studies.map((x) => x.patient_id));
    data.patients = data.patients.filter((x) => patientIds.has(x.id));
    let seriesIds = new Set(
      data.series.filter((x) => studyIds.has(x.study_id)).map((x) => x.id),
    );
    data.series = data.series.filter((x) => seriesIds.has(x.id));
    let instanceIds = new Set(
      data.instances
        .filter((x) => seriesIds.has(x.series_id))
        .map((x) => x.id),
    );
    data.instances = data.instances.filter((x) => instanceIds.has(x.id));
    data.assessments = data.assessments.filter((x) =>
      seriesIds.has(x.series_id),
    );
    data.lesions = data.lesions.filter((x) => seriesIds.has(x.series_id));
    let lesionIds = new Set(data.lesions.map((x) => x.id));
    data.boxes = data.boxes.filter(
      (x) =>
        lesionIds.has(x.lesion_instance_id) &&
        instanceIds.has(x.sop_instance_uid),
    );
    return data;
  }
  async function refresh(scope = loadedStudy.current) {
    scope = reviewSubmission?.study_uid || scope;
    loadedStudy.current = scope;
    let data = await loadState(scope);
    const labels = {
      "ACL 损伤": "前交叉韧带损伤（ACL）",
      ACL损伤: "前交叉韧带损伤（ACL）",
      "PCL 损伤": "后交叉韧带损伤（PCL）",
      PCL损伤: "后交叉韧带损伤（PCL）",
      "MCL 损伤": "内侧副韧带损伤（MCL）",
      MCL损伤: "内侧副韧带损伤（MCL）",
      "LCL 损伤": "外侧副韧带损伤（LCL）",
      LCL损伤: "外侧副韧带损伤（LCL）",
    };
    data.diseases = data.diseases.map((d) => ({
      ...d,
      disease_name: labels[d.disease_name] || d.disease_name,
    }));
    if (!reviewSubmission) {
      let hidden = locallyHiddenStudies();
      data.studies = data.studies.filter((x) => !hidden.has(x.id));
      let visibleStudyIds = new Set(data.studies.map((x) => x.id));
      data.series = data.series.filter((x) => visibleStudyIds.has(x.study_id));
      let visibleSeriesIds = new Set(data.series.map((x) => x.id));
      data.instances = data.instances.filter((x) => visibleSeriesIds.has(x.series_id));
      data.assessments = data.assessments.filter((x) => visibleSeriesIds.has(x.series_id));
      data.lesions = data.lesions.filter((x) => visibleSeriesIds.has(x.series_id));
      let visibleLesions = new Set(data.lesions.map((x) => x.id));
      data.boxes = data.boxes.filter((x) => visibleLesions.has(x.lesion_instance_id));
      let visiblePatients = new Set(data.studies.map((x) => x.patient_id));
      data.patients = data.patients.filter((x) => visiblePatients.has(x.id));
    }
    let prepared = restrictToReviewStudy(data);
    set(prepared);
    return prepared;
  }
  async function refreshSubmissions() {
    let r = await workflowRequest("/submissions");
    setSubmissions(r.submissions || []);
  }
  E(() => {
    refresh(reviewSubmission?.study_uid || "").catch((e) => msg(String(e)));
    refreshSubmissions().catch((e) => msg(String(e)));
  }, []);
  E(() => {
    if (reviewSubmission) return;
    let update = () => {
      if (document.visibilityState === "visible")
        refreshSubmissions().catch(() => undefined);
    };
    let timer = setInterval(update, 15000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [reviewSubmission?.id]);
  E(() => {
    let cancelled = false;
    if (!activeStudyId || !studyImageIds.length) {
      setLocalImages({ available: 0, total: studyImageIds.length, checking: false });
      return;
    }
    setLocalImages((value) => ({ ...value, checking: true }));
    localImageAvailability(studyImageIds)
      .then((value) => {
        if (!cancelled) setLocalImages({ ...value, checking: false });
      })
      .catch(() => {
        if (!cancelled)
          setLocalImages({ available: 0, total: studyImageIds.length, checking: false });
      });
    return () => {
      cancelled = true;
    };
  }, [activeStudyId, studyImageIds.join("|"), renderVersion]);

  async function importDicom(input: HTMLInputElement) {
    if (!input.files?.length) return;
    msg("正在读取本机 DICOM");
    try {
      let result = await importLocal(input.files, {
        localOnly: !!reviewSubmission,
        expectedStudyUid: reviewSubmission ? activeStudyId || undefined : undefined,
        onProgress: msg,
      });
      if (!result.imported && result.wrongStudyCount) {
        msg("所选 DICOM 与当前检查不匹配");
        alert(
          `导入的 DICOM 不属于当前 Patient ID：${patientIdHint}，请选择正确的检查。`,
        );
        return;
      }
      if (!result.imported) {
        msg("未读取到当前检查的有效 DICOM");
        alert(
          `没有读取到 Patient ID：${patientIdHint} 对应检查的有效 DICOM，请确认选择正确且文件未损坏。`,
        );
        return;
      }
      if (result.wrongStudyCount) {
        alert(
          `已忽略 ${result.wrongStudyCount} 个不属于当前检查的 DICOM 文件。`,
        );
      }
      if (result.state) set(restrictToReviewStudy(result.state));
      if (!reviewSubmission) {
        let importedStudy = result.studyIds?.[0] || activeStudyId || loadedStudy.current;
        // Load the imported study first, then select from that returned state.
        // Clearing sid before refresh lets the automatic selector race against
        // this request and select the previous study again.
        let importedState = await refresh(importedStudy),
          firstImportedSeries = importedState.series.find(
            (item) => item.study_id === importedStudy,
          );
        series(firstImportedSeries?.id || "");
        slice(0);
        lesion("");
        CB(null);
      }
      RV((value) => value + 1);
      msg(`本机已读取 ${result.imported} 张，跳过 ${result.skipped.length} 个文件`);
    } catch (error) {
      msg("DICOM 导入失败：" + String(error));
      alert("DICOM 导入失败：" + String(error));
    } finally {
      input.value = "";
    }
  }
  E(() => {
    if (s.series.length) {
      let current = s.series.find(
        (x) =>
          x.id === sid &&
          (!reviewSubmission || x.study_id === reviewSubmission.study_uid),
      );
      let first =
        current ||
        (reviewSubmission
          ? s.series.find((x) => x.study_id === reviewSubmission.study_uid)
          : s.series[0]);
      if (first && sid !== first.id) {
        series(first.id);
        slice(0);
      }
      if (first && loadedStudy.current !== first.study_id)
        refresh(first.study_id).catch((e) => msg(String(e)));
    }
  }, [reviewSubmission?.id, s.series.length, sid]);
  E(() => {
    let visible = () => {
      if (
        document.visibilityState === "visible" &&
        loadedStudy.current &&
        !pending &&
        !busy &&
        !drag.current
      )
        refresh(loadedStudy.current).catch((e) => msg(String(e)));
    };
    document.addEventListener("visibilitychange", visible);
    return () => document.removeEventListener("visibilitychange", visible);
  }, [pending, busy]);
  function prepareRecord(kind, d) {
    let prepared = { ...d };
    prepared.id ||=
      kind === "assessments"
        ? [
            prepared.series_id,
            prepared.disease_type_id,
            prepared.disease_type_id === "MENISCUS_INJURY"
              ? prepared.target_key
              : "OVERALL",
          ].join("|")
        : newId();
    return prepared;
  }
  function optimistic(kind, prepared) {
    set((state) => {
      let list = state[kind] || [],
        next = list.some((x) => x.id === prepared.id)
          ? list.map((x) => (x.id === prepared.id ? prepared : x))
          : [...list, prepared];
      return { ...state, [kind]: next };
    });
  }
  async function save(
    kind,
    d,
    record = true,
    beforeOverride: any = undefined,
    alreadyOptimistic = false,
    background = false,
  ) {
    if (editLocked) throw Error(pendingAnnotatorReview ? "该检查正在等待审核，审核完成前不能修改标注" : "该审核记录为只读，不能修改标注");
    let prepared = prepareRecord(kind, d);
    let before =
      beforeOverride === undefined
        ? s[kind].find((x) => x.id === prepared.id) || null
        : beforeOverride;
    if (!alreadyOptimistic) optimistic(kind, prepared);
    (background ? SP : P)((n) => n + 1);
    setSyncError("");
    let request = req("/" + kind, "PUT", prepared);
    pendingSaves.current.add(request);
    try {
      if (!background) msg("后台保存中");
      let r = await request;
      if (record) {
        H((h) => [...h, { kind, before, after: r }]);
        F([]);
      }
      set((state) => ({
        ...state,
        [kind]: (state[kind] || []).map((x) => (x.id === prepared.id ? r : x)),
      }));
      if (!background) msg("草稿已自动保存，可点击保存标注确认");
      return r;
    } catch (e) {
      set((state) => {
        let list = state[kind] || [];
        return {
          ...state,
          [kind]: before
            ? list.map((x) => (x.id === prepared.id ? before : x))
            : list.filter((x) => x.id !== prepared.id),
        };
      });
      msg("保存失败，已回滚：" + String(e));
      setSyncError(String(e));
      throw e;
    } finally {
      pendingSaves.current.delete(request);
      (background ? SP : P)((n) => n - 1);
    }
  }
  function runDebounced(key: string) {
    let entry = debounceSaves.current.get(key);
    if (!entry) return Promise.resolve();
    clearTimeout(entry.timer);
    debounceSaves.current.delete(key);
    Q((n) => Math.max(0, n - 1));
    return save(
      entry.kind,
      entry.latest,
      entry.record,
      entry.before,
      true,
      true,
    );
  }
  function debounceSave(kind, d, record = true) {
    if (editLocked) return;
    let prepared = prepareRecord(kind, d);
    let key = kind + ":" + prepared.id;
    let entry = debounceSaves.current.get(key);
    if (!entry) {
      entry = {
        kind,
        before: s[kind].find((x) => x.id === prepared.id) || null,
        record,
      };
      debounceSaves.current.set(key, entry);
      Q((n) => n + 1);
    } else clearTimeout(entry.timer);
    entry.latest = prepared;
    optimistic(kind, prepared);
    setSyncError("");
    entry.timer = setTimeout(() => {
      runDebounced(key).catch(() => undefined);
    }, 1000);
  }
  async function flushDebounced() {
    let keys = [...debounceSaves.current.keys()];
    if (keys.length) await Promise.all(keys.map(runDebounced));
  }
  async function backgroundRequest<T>(request: Promise<T>) {
    SP((n) => n + 1);
    pendingSaves.current.add(request);
    try {
      return await request;
    } finally {
      pendingSaves.current.delete(request);
      SP((n) => Math.max(0, n - 1));
    }
  }
  const builtinCodes = new Set([
    "ACL_INJURY",
    "PCL_INJURY",
    "MCL_INJURY",
    "LCL_INJURY",
    "PATELLAR_LIGAMENT_INJURY",
    "PATELLAR_RETINACULUM_INJURY",
    "QUADRICEPS_TENDON_INJURY",
    "POPLITEUS_TENDON_INJURY",
    "MENISCUS_INJURY",
    "CARTILAGE_INJURY",
    "HOFFA_FAT_PAD_ABNORMALITY",
    "SYNOVIAL_ABNORMALITY",
    "JOINT_EFFUSION",
    "BONE_INJURY",
    "SUBCHONDRAL_INJURY",
  ]);
  function applicable(fields, values) {
    return (fields || []).filter(
      (f) =>
        !f.hide_when ||
        !Object.entries(f.hide_when).some(([k, v]) => values[k] === v),
    );
  }
  function empty(value) {
    return (
      value === undefined ||
      value === null ||
      value === "" ||
      (Array.isArray(value) && !value.filter((x) => x !== "").length)
    );
  }
  function missing(config, fields, values) {
    return applicable(fields, values)
      .filter(
        (f) =>
          (builtinCodes.has(config.id) || f.required) &&
          empty(values[f.field_code]),
      )
      .map((f) => f.field_name);
  }
  function progress(config, fields, values) {
    let fs = applicable(fields, values).filter(
        (f) => builtinCodes.has(config.id) || f.required,
      ),
      miss = missing(config, fields, values);
    return (
      <div
        className={"completion " + (miss.length ? "incomplete" : "complete")}
        role="status"
      >
        {miss.length
          ? `待填写 ${fs.length - miss.length}/${fs.length} · 缺少：${miss.join("、")}`
          : "适用必填属性已填写完整"}
      </div>
    );
  }
  function seriesFindingLabels(seriesId: string) {
    let assessments = s.assessments.filter((x) => x.series_id === seriesId),
      synovial = assessments.find(
        (x) => x.disease_type_id === "SYNOVIAL_ABNORMALITY",
      )?.attributes_json?.["异常程度"],
      effusion = assessments.find(
        (x) => x.disease_type_id === "JOINT_EFFUSION",
      )?.attributes_json?.["积液程度"],
      labels: string[] = [];
    if (synovial && synovial !== "正常") labels.push("滑膜");
    if (effusion && effusion !== "无积液") labels.push("积液");
    return labels;
  }
  function allowLeave() {
    return true;
  }
  function issues(scope) {
    let result = [];
    let started = s.assessments.filter((a) => !scope || a.study_id === scope);
    for (let a of started) {
      let d = s.diseases.find((d) => d.id === a.disease_type_id);
      if (!d) continue;
      let miss = missing(d, d.overall_fields, a.attributes_json || {});
      if (miss.length)
        result.push({
          study_id: a.study_id,
          disease: d.id,
          series: a.series_id,
          target: a.target_key,
          label: d.disease_name + " 整体评价（" + a.target_key + "）",
          missing: miss,
        });
    }
    for (let l of s.lesions.filter(
      (l) =>
        (!scope || l.study_id === scope) &&
        s.boxes.some((b) => b.lesion_instance_id === l.id),
    )) {
      let d = s.diseases.find((d) => d.id === l.disease_type_id);
      if (!d) continue;
      let miss = missing(d, d.lesion_fields, l.attributes_json || {});
      if (miss.length)
        result.push({
          study_id: l.study_id,
          disease: d.id,
          lesion: l.id,
          series: l.series_id,
          label: d.disease_name + " 病灶 " + l.id.slice(0, 8),
          missing: miss,
        });
      if (
        d.overall_fields.length &&
        !started.some(
          (a) =>
            a.study_id === l.study_id &&
            a.series_id === l.series_id &&
            a.disease_type_id === d.id &&
            (d.id !== "MENISCUS_INJURY" ||
              a.target_key === l.tissue_type ||
              a.target_key ===
                {
                  内侧半月板: "MEDIAL_MENISCUS",
                  外侧半月板: "LATERAL_MENISCUS",
                }[l.attributes_json?.["半月板类型"]]),
        )
      ) {
        result.push({
          study_id: l.study_id,
          disease: d.id,
          series: l.series_id,
          label: d.disease_name + " 整体评价",
          missing: ["尚未填写整体评价"],
        });
      }
    }
    return result;
  }
  let currentIssues = issues(study);
  let assessmentReady =
    dis?.box_policy === "NONE" ||
    s.lesions.some(
      (l) =>
        l.series_id === sid &&
        l.disease_type_id === di &&
        (di !== "MENISCUS_INJURY" || l.target_key === target) &&
        s.boxes.some((b) => b.lesion_instance_id === l.id),
    );
  function checkSummary(scope, action) {
    let list = issues(scope);
    return (
      !list.length ||
      confirm(
        action +
          "前检查：共 " +
          list.length +
          " 项未完成。\n" +
          list
            .slice(0, 12)
            .map((x) => x.label + "：" + x.missing.join("、"))
            .join("\n") +
          "\n\n确定：" +
          (action === "保存" ? "保存为未完成草稿" : "导出草稿") +
          "；取消：返回补填。",
      )
    );
  }
  function locateIssue(issue) {
    if (!allowLeave()) return;
    let targetSeries =
      issue.series || s.series.find((x) => x.study_id === issue.study_id)?.id;
    if (targetSeries !== sid) {
      series(targetSeries);
      slice(0);
    }
    disease(issue.disease);
    if (issue.target && issue.disease === "MENISCUS_INJURY") T(issue.target);
    if (issue.lesion) {
      let box = s.boxes.find((b) => b.lesion_instance_id === issue.lesion);
      if (box) {
        let imgs = s.instances
          .filter((x) => x.series_id === targetSeries)
          .sort((a, b) => a.order - b.order);
        slice(
          Math.max(
            0,
            imgs.findIndex((x) => x.id === box.sop_instance_uid),
          ),
        );
        setTimeout(() => selectBox(box), 0);
      }
    }
  }
  function exportIssues() {
    return issues(study).filter((x) =>
      x.series ? x.series === sid : !x.lesion,
    );
  }
  async function exportCurrent(fmt) {
    if (!sid || pending || busy) return;
    let missing = exportIssues();
    if (missing.length) {
      IO(true);
      alert("当前序列仍有 " + missing.length + " 项标注未完成，请补全后导出。");
      return;
    }
    let handle;
    try {
      const extension = fmt === "csv" ? "csv" : "json";
      const filename =
        "knee_" + sid + (fmt === "coco" ? ".coco" : "") + "." + extension;
      if ((window as any).showSaveFilePicker)
        handle = await (window as any).showSaveFilePicker({
          suggestedName: filename,
          types: [
            {
              description: fmt.toUpperCase(),
              accept: {
                [fmt === "csv" ? "text/csv" : "application/json"]: [
                  "." + extension,
                ],
              },
            },
          ],
        });
      B(true);
      let blob = await exportLocal(fmt, sid);
      if (handle) {
        let writer = await handle.createWritable();
        await writer.write(blob);
        await writer.close();
      } else {
        let url = URL.createObjectURL(blob),
          link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      msg("当前序列 " + fmt.toUpperCase() + " 已导出");
    } catch (error) {
      if (error.name !== "AbortError") {
        msg("导出失败：" + String(error));
        alert("导出失败：" + String(error));
      }
    } finally {
      B(false);
    }
  }
  async function commit(scope?: string) {
    await flushDebounced();
    if (pendingSaves.current.size) await Promise.all([...pendingSaves.current]);
    let incomplete = issues(scope);
    if (!checkSummary(scope, "保存")) throw Error("已取消保存，请补填属性");
    let r = await req("/project/save", "POST", {
      assessment_status: incomplete.length ? "DRAFT" : "COMPLETE",
      incomplete_items: incomplete,
      study_id: scope || null,
    });
    msg(
      (incomplete.length
        ? "未完成草稿已保存到服务器数据库 · "
        : "标注已保存到服务器数据库 · ") +
        new Date(r.saved_at).toLocaleTimeString(),
    );
    return r;
  }
  async function submitReview() {
    if (!study) throw Error("请先选择要提交的检查");
    if (pending) throw Error("请等待自动保存完成");
    if (
      !confirm(
        "确定提交当前检查进行审核吗？提交后在审核通过或驳回前不能修改标注。",
      )
    )
      return;
    B(true);
    try {
      await commit(study);
      let r = await workflowRequest(
        "/studies/" + encodeURIComponent(study) + "/submit",
        "POST",
        {},
      );
      await refreshSubmissions();
      alert("提交审核成功");
      msg("已提交审核 · 修订 " + r.submission.revision);
    } catch (e) {
      let list = (e as any).issues || [];
      if (list.length) alert("提交检查未通过：\n" + list.join("\n"));
      throw e;
    } finally {
      B(false);
    }
  }
  async function reviewDecision(action) {
    if (!reviewSubmission || readOnlyReview) return;
    if (
      !confirm(
        action === "approve"
          ? "确定保存当前修改并审核通过吗？"
          : "确定保存当前修改并驳回吗？",
      )
    )
      return;
    let reason = "";
    if (action === "reject") {
      reason = prompt("请输入驳回理由") || "";
      if (!reason) {
        alert("驳回操作已取消：必须填写驳回理由");
        return;
      }
    }
    B(true);
    try {
      await commit(reviewSubmission.study_uid);
      await workflowRequest(
        "/submissions/" + reviewSubmission.id + "/review",
        "POST",
        { action, reason },
      );
      alert(action === "approve" ? "审核通过成功" : "已驳回并记录理由");
      await onReviewed?.();
    } catch (e) {
      alert("审核失败：" + String(e));
    } finally {
      B(false);
    }
  }
  E(() => {
    if (!reviewSubmission) return;
    let handle = (event: any) => reviewDecision(event.detail);
    window.addEventListener("review-decision", handle);
    return () => window.removeEventListener("review-decision", handle);
  }, [reviewSubmission?.id, pending, busy]);
  function navigateReviewChange(item: any) {
      let normalizedLabel = String(item?.label || "").replace(/第\s*(\d+)\s*张框/g, "第 $1 个切片"),
        targetSeries = s.series.find((x) => x.id === item.series_uid) ||
          s.series.find((x) => normalizedLabel.startsWith(`${x.number} · ${x.description} ·`));
      if (!targetSeries) return;
      series(targetSeries.id);
      let targetDisease = s.diseases.find((x) => x.id === item.disease_code) ||
        s.diseases.find((x) => normalizedLabel.includes(` · ${x.disease_name} ·`) || normalizedLabel.endsWith(` · ${x.disease_name}`));
      if (targetDisease) disease(targetDisease.id);
      if (item.lesion_id) {
        lesion(item.lesion_id);
        expand(item.lesion_id);
      }
      if (item.kind === "box" || /第\s*\d+\s*个切片/.test(normalizedLabel)) {
        let targetImages = s.instances
            .filter((x) => x.series_id === targetSeries.id)
            .sort((a, b) => a.order - b.order),
          labelIndex = Number(normalizedLabel.match(/第\s*(\d+)\s*个切片/)?.[1] || 0) - 1,
          uidIndex = item.sop_instance_uid
            ? targetImages.findIndex((x) => x.id === item.sop_instance_uid)
            : -1,
          snapshotIndex = Number(item.slice_index || 0) - 1,
          targetIndex = uidIndex >= 0 ? uidIndex : snapshotIndex >= 0 ? snapshotIndex : labelIndex,
          targetImage = targetImages[targetIndex],
          box = item._changeType === "deleted" ? null :
            s.boxes.find((x) => x.id === item.box_id) ||
            s.boxes.find((x) => x.sop_instance_uid === targetImage?.id && x.lesion_instance_id === item.lesion_id) ||
            s.boxes.find((x) => x.sop_instance_uid === targetImage?.id &&
              s.lesions.some((l) => l.id === x.lesion_instance_id && l.disease_type_id === targetDisease?.id));
        if (targetIndex >= 0) slice(targetIndex);
        if (item._changeType === "deleted") {
          lesion("");
          CB(null);
        }
        setTimeout(() => {
          // The sid-change effect deliberately clears stale box selection. Apply
          // the review target after that effect has completed so the requested
          // box remains selected and highlighted in the destination series.
          if (box) {
            lesion(box.lesion_instance_id);
            expand(box.lesion_instance_id);
            CB({ ...box, series_id: targetSeries.id });
          }
          setTimeout(() => {
            document.querySelector(`[data-box-id="${CSS.escape(box?.id || item.box_id || "")}"]`)
              ?.scrollIntoView({ behavior: "smooth", block: "center" });
          }, 50);
        }, 250);
      } else {
        // Overall attributes do not carry a slice. When this disease has local
        // instances, use one current box as a visual anchor; diseases such as
        // synovium/effusion remain series-level and only reveal the form.
        let targetImages = s.instances
            .filter((x) => x.series_id === targetSeries.id)
            .sort((a, b) => a.order - b.order),
          relatedLesions = new Set(
            s.lesions
              .filter((x) =>
                x.series_id === targetSeries.id &&
                x.disease_type_id === targetDisease?.id,
              )
              .map((x) => x.id),
          ),
          anchorBox = item._changeType === "deleted"
            ? null
            : s.boxes
                .filter((x) => relatedLesions.has(x.lesion_instance_id))
                .sort((a, b) =>
                  targetImages.findIndex((image) => image.id === a.sop_instance_uid) -
                  targetImages.findIndex((image) => image.id === b.sop_instance_uid),
                )[0],
          anchorIndex = anchorBox
            ? targetImages.findIndex((x) => x.id === anchorBox.sop_instance_uid)
            : -1;
        if (anchorIndex >= 0) slice(anchorIndex);
        if (item._changeType === "deleted") {
          lesion("");
          CB(null);
        }
        setTimeout(() => {
          if (anchorBox) {
            lesion(anchorBox.lesion_instance_id);
            expand(anchorBox.lesion_instance_id);
            CB({ ...anchorBox, series_id: targetSeries.id });
          }
          document.querySelector("main>aside:last-child .overall-annotation")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 250);
      }
  }
  async function removeData(kind, id) {
    if (
      !confirm(
        "确定从当前浏览器移除该检查的本机影像？\n服务器上的检查和标注不会删除，重新导入同一检查后会自动加载已有标注。",
      )
    )
      return;
    B(true);
    try {
      let targetSeries = s.series.filter((x) => x.study_id === id).map((x) => x.id);
      let targetUids = s.instances
        .filter((x) => targetSeries.includes(x.series_id))
        .map((x) => x.id);
      if (!reviewSubmission) {
        // Remove the study from the ordinary user's view in the same render as
        // the click. Do not leave the old series mounted while IndexedDB and
        // the server catalog refresh finish in the background.
        set((state) => {
          let seriesIds = new Set(
              state.series.filter((x) => x.study_id === id).map((x) => x.id),
            ),
            lesionIds = new Set(
              state.lesions.filter((x) => seriesIds.has(x.series_id)).map((x) => x.id),
            ),
            studies = state.studies.filter((x) => x.id !== id),
            patientIds = new Set(studies.map((x) => x.patient_id));
          return {
            ...state,
            studies,
            patients: state.patients.filter((x) => patientIds.has(x.id)),
            series: state.series.filter((x) => !seriesIds.has(x.id)),
            instances: state.instances.filter((x) => !seriesIds.has(x.series_id)),
            assessments: state.assessments.filter((x) => !seriesIds.has(x.series_id)),
            lesions: state.lesions.filter((x) => !seriesIds.has(x.series_id)),
            boxes: state.boxes.filter((x) => !lesionIds.has(x.lesion_instance_id)),
          };
        });
      }
      await removeLocalStudyImages(id, targetUids);
      series("");
      slice(0);
      lesion("");
      H([]);
      F([]);
      vp.current?.element && engine.current?.disableElement("stack");
      engine.current?.destroy();
      engine.current = null;
      vp.current = null;
      imageMsg("请选择序列");
      if (reviewSubmission) {
        RV((value) => value + 1);
        setLocalImages({ available: 0, total: targetUids.length, checking: false });
        msg("已从当前浏览器移除影像；服务器标注仍保留，可重新导入查看");
      } else {
        await refresh("");
        msg("已从当前浏览器列表移除；重新导入同一检查可恢复显示和标注");
      }
    } catch (e) {
      if (!reviewSubmission) refresh("").catch(() => undefined);
      msg("删除未完成：" + String(e));
    } finally {
      B(false);
    }
  }
  // Selecting an existing box can update disease, but must never activate drawing.
  E(() => {
    mode("select");
    setDrawLesion("");
  }, [sid, di]);
  E(() => {
    expand(lid);
  }, [lid]);
  E(() => {
    lesion("");
    V(null);
    CB(null);
  }, [sid]);
  E(() => {
    V(null);
    drag.current = null;
    if (liveRect.current) liveRect.current.style.display = "none";
  }, [idx]);
  E(() => {
    if (!images.length) {
      if (vp.current?.element) engine.current?.disableElement("stack");
      engine.current?.destroy();
      engine.current = null;
      vp.current = null;
      imageMsg(activeStudyId ? "当前检查尚未加载影像" : "请选择序列");
      return;
    }
    let cancelled = false;
    (async () => {
      await prepareViewer();
      if (cancelled || !el.current) return;
      if (!engine.current) {
        engine.current = new RenderingEngine("knee");
        engine.current.enableElement({
          viewportId: "stack",
          type: Enums.ViewportType.STACK,
          element: el.current,
        });
        vp.current = engine.current.getViewport("stack");
      }
      if (images.length) {
        imageMsg("正在加载首张影像…");
        await vp.current.setStack(
          images.map((x) => imageId(x.id)),
          idx,
        );
        if (cancelled) return;
        engine.current.resize(true, false);
        vp.current.resetCamera();
        vp.current.render();
        imageMsg("");
      }
    })().catch((e) => {
      console.error("DICOM load failed", e);
      imageMsg("影像加载失败：" + (e?.message || String(e)));
    });
    return () => {
      cancelled = true;
    };
  }, [
    sid,
    images
      .map((x) => {
        try {
          return imageId(x.id);
        } catch {
          return x.id;
        }
      })
      .join(","),
  ]);
  E(() => {
    if (vp.current && im)
      vp.current
        .setImageIdIndex(idx)
        .then(() => vp.current.render())
        .catch((e) => msg(String(e)));
  }, [idx]);
  function projected(x, y) {
    try {
      let data = vp.current?.getImageData()?.imageData;
      if (!data) return null;
      return vp.current.worldToCanvas(data.indexToWorld([x, y, 0]));
    } catch {
      return null;
    }
  }
  E(() => {
    if (!el.current) return;
    let observer = new ResizeObserver(() => {
      if (engine.current) {
        engine.current.resize(true, false);
        vp.current?.render();
      }
    });
    observer.observe(el.current);
    return () => observer.disconnect();
  }, []);
  E(() => {
    let viewer = el.current;
    if (!viewer) return;
    let move = (e: PointerEvent) => {
      let d = drag.current;
      if (!d || tool !== "draw" || !liveRect.current) return;
      let bounds = viewer.getBoundingClientRect(),
        x = e.clientX - bounds.left,
        y = e.clientY - bounds.top,
        r = liveRect.current;
      r.setAttribute("x", String(Math.min(d.sx, x)));
      r.setAttribute("y", String(Math.min(d.sy, y)));
      r.setAttribute("width", String(Math.abs(x - d.sx)));
      r.setAttribute("height", String(Math.abs(y - d.sy)));
      e.stopPropagation();
    };
    viewer.addEventListener("pointermove", move);
    return () => viewer.removeEventListener("pointermove", move);
  }, [tool]);
  function lesionColor(id) {
    let l = s.lesions.find((x) => x.id === id);
    if (l?.color) return l.color;
    let hash = 2166136261;
    for (let ch of id || "")
      hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619);
    return `hsl(${(hash >>> 0) % 360},85%,65%)`;
  }
  function rectangle(b, key, color) {
    let a = projected(b.x_min, b.y_min),
      z = projected(b.x_max, b.y_max);
    if (!a || !z) return null;
    let active = b.lesion_instance_id === lid && !b.ghost;
    let x = Math.min(a[0], z[0]),
      y = Math.min(a[1], z[1]),
      w = Math.abs(z[0] - a[0]),
      h = Math.abs(z[1] - a[1]);
    return (
      <g key={key} opacity={b.ghost ? 0.5 : 1}>
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          fill={active ? color : "none"}
          fillOpacity={active ? 0.12 : 0}
          stroke={color}
          strokeWidth={active ? 3 : 2}
          strokeDasharray={b.ghost ? "6 4" : undefined}
        />
        {active &&
          [
            [x, y],
            [x + w, y],
            [x, y + h],
            [x + w, y + h],
          ].map(([cx, cy], i) => (
            <rect
              key={i}
              x={cx - 4}
              y={cy - 4}
              width="8"
              height="8"
              fill={color}
              stroke="white"
            />
          ))}
        <text x={x} y={y - 5} fill={color} fontSize="13">
          {b.ghost
            ? "待粘贴 · " + b.lesion_instance_id?.slice(0, 8)
            : key === "preview"
              ? "绘制中"
              : b.lesion_instance_id?.slice(0, 8)}
        </text>
      </g>
    );
  }
  function startPointer(e) {
    if (tool === "draw" && di === "MENISCUS_INJURY" && !target) {
      msg("请先选择内侧或外侧半月板");
      return;
    }
    if (!im || !vp.current?.getImageData()) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    let p = point(e);
    if (tool === "select") {
      let current = s.boxes
        .filter((b) => b.sop_instance_uid === im.id)
        .sort(
          (a, b) =>
            Number(b.lesion_instance_id === lid) -
            Number(a.lesion_instance_id === lid),
        );
      let rect = el.current.getBoundingClientRect(),
        screen = [e.clientX - rect.left, e.clientY - rect.top];
      for (let b of current) {
        for (let corner of [
          ["x_min", "y_min"],
          ["x_max", "y_min"],
          ["x_min", "y_max"],
          ["x_max", "y_max"],
        ]) {
          let q = projected(b[corner[0]], b[corner[1]]);
          if (q && Math.hypot(q[0] - screen[0], q[1] - screen[1]) < 12) {
            selectBox(b);
            if (editLocked) return;
            drag.current = {
              edit: b,
              corner,
              p,
              x: e.clientX,
              y: e.clientY,
            };
            V({ ...b });
            return;
          }
        }
      }
      for (let b of current) {
        if (
          p[0] >= b.x_min &&
          p[0] <= b.x_max &&
          p[1] >= b.y_min &&
          p[1] <= b.y_max
        ) {
          selectBox(b);
          if (editLocked) return;
          drag.current = { edit: b, p, x: e.clientX, y: e.clientY };
          V({ ...b });
          return;
        }
      }
      lesion("");
      return;
    }
    if (editLocked && tool === "draw") return;
    if (tool === "draw" && (!dis || dis.box_policy === "NONE")) {
      msg("请先选择支持绘框的病害");
      return;
    }
    let bounds = el.current!.getBoundingClientRect();
    drag.current = {
      p,
      x: e.clientX,
      y: e.clientY,
      sx: e.clientX - bounds.left,
      sy: e.clientY - bounds.top,
      camera: vp.current.getCamera(),
      props: vp.current.getProperties(),
    };
    if (tool === "draw") {
      if (!liveRect.current) {
        let svg = el.current!.querySelector("svg"),
          r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        r.setAttribute("fill", "rgba(255,224,102,.12)");
        r.setAttribute("stroke", "#ffe066");
        r.setAttribute("stroke-width", "2");
        r.setAttribute("stroke-dasharray", "6 4");
        svg?.appendChild(r);
        liveRect.current = r;
      }
      let r = liveRect.current;
      r.style.display = "";
      r.setAttribute("x", String(drag.current.sx));
      r.setAttribute("y", String(drag.current.sy));
      r.setAttribute("width", "0");
      r.setAttribute("height", "0");
    }
  }
  function selectLesionEntry(l) {
    let box =
      s.boxes.find(
        (b) =>
          b.lesion_instance_id === l.id &&
          b.id === lastSelectedBoxes.current[l.id],
      ) ||
      s.boxes.find(
        (b) => b.lesion_instance_id === l.id && b.sop_instance_uid === im?.id,
      ) ||
      s.boxes.find((b) => b.lesion_instance_id === l.id);
    if (box) {
      let index = images.findIndex((i) => i.id === box.sop_instance_uid);
      if (index >= 0) slice(index);
      selectBox(box);
    }
  }
  function selectBox(b) {
    lastSelectedBoxes.current[b.lesion_instance_id] = b.id;
    setDrawLesion("");
    expand(b.lesion_instance_id);
    if (b.lesion_instance_id !== lid && !allowLeave()) return;
    let l = s.lesions.find((x) => x.id === b.lesion_instance_id);
    if (l) {
      if (l.disease_type_id === "MENISCUS_INJURY")
        T(
          l.tissue_type ||
            { 内侧半月板: "MEDIAL_MENISCUS", 外侧半月板: "LATERAL_MENISCUS" }[
              l.attributes_json?.["半月板类型"]
            ] ||
            "",
        );
      mode("select");
      disease(l.disease_type_id);
      lesion(l.id);
      CB({ ...b, series_id: l.series_id });
    }
  }
  function editedBox(d, p) {
    let b = { ...d.edit };
    if (d.corner) {
      b[d.corner[0]] = p[0];
      b[d.corner[1]] = p[1];
      let x = Math.min(b.x_min, b.x_max),
        y = Math.min(b.y_min, b.y_max);
      b.x_max = Math.max(b.x_min, b.x_max);
      b.y_max = Math.max(b.y_min, b.y_max);
      b.x_min = x;
      b.y_min = y;
    } else {
      let dx = Math.max(-b.x_min, Math.min(im.width - b.x_max, p[0] - d.p[0])),
        dy = Math.max(-b.y_min, Math.min(im.height - b.y_max, p[1] - d.p[1]));
      b.x_min += dx;
      b.x_max += dx;
      b.y_min += dy;
      b.y_max += dy;
    }
    return b;
  }
  function forms(fields, values, change) {
    return fields?.map((f) => {
      if (
        f.hide_when &&
        Object.entries(f.hide_when).some(([k, v]) => values[k] === v)
      )
        return null;
      let options = f.options_by
        ? f.options_by.values[values[f.options_by.field]] || []
        : f.options;
      return (
        <label
          className={
            empty(values[f.field_code]) &&
            (builtinCodes.has(dis?.id) || f.required)
              ? "missing-field"
              : ""
          }
          key={f.field_code}
        >
          {f.field_name}
          {options?.length ? (
            <select
              disabled={editLocked}
              multiple={f.field_type === "multi_select"}
              value={
                values[f.field_code] ??
                (f.field_type === "multi_select" ? [] : "")
              }
              onChange={(e) =>
                change({
                  ...values,
                  [f.field_code]:
                    f.field_type === "multi_select"
                      ? Array.from(e.target.selectedOptions).map((o) => o.value)
                      : e.target.value,
                })
              }
            >
              <option value="" disabled>
                未评估 / 请选择
              </option>
              {options.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              disabled={editLocked}
              type={
                f.field_type === "number"
                  ? "number"
                  : f.field_type === "boolean"
                    ? "checkbox"
                    : "text"
              }
              checked={values[f.field_code] === true}
              value={values[f.field_code] ?? ""}
              onChange={(e) =>
                change({
                  ...values,
                  [f.field_code]:
                    f.field_type === "boolean"
                      ? e.target.checked
                      : f.field_type === "number"
                        ? Number(e.target.value)
                        : e.target.value,
                })
              }
            />
          )}
        </label>
      );
    });
  }
  function point(e) {
    let rect = el.current!.getBoundingClientRect();
    let world = vp.current.canvasToWorld([
      e.clientX - rect.left,
      e.clientY - rect.top,
    ]);
    let p = vp.current.getImageData().imageData.worldToIndex(world);
    return [
      Math.max(0, Math.min(im.width, p[0])),
      Math.max(0, Math.min(im.height, p[1])),
    ];
  }
  async function end(e) {
    if (!drag.current || !im) return;
    let a = drag.current;
    drag.current = null;
    if (liveRect.current) liveRect.current.style.display = "none";
    V(null);
    if (editLocked && (a.edit || tool === "draw")) return;
    if (a.edit) {
      if (Math.hypot(e.clientX - a.x, e.clientY - a.y) < 5) return;
      let b = editedBox(a, point(e));
      let geometryChanged = ["x_min", "y_min", "x_max", "y_max"].some(
        (key) => Math.abs(Number(b[key]) - Number(a.edit[key])) > 0.01,
      );
      if (
        geometryChanged &&
        b.x_max - b.x_min >= 1 &&
        b.y_max - b.y_min >= 1
      ) {
        optimistic("boxes", b);
        await save("boxes", b, true, a.edit, true, true);
      }
      return;
    }
    if (tool !== "draw") {
      RV((n) => n + 1);
      return;
    }
    if (!dis) {
      msg("病害配置尚未加载，请刷新页面后重试");
      return;
    }
    let p = point(e);
    if (Math.abs(p[0] - a.p[0]) < 2 || Math.abs(p[1] - a.p[1]) < 2) return;
    let l =
        drawLesion &&
        s.lesions.find(
          (l) =>
            l.id === drawLesion &&
            l.series_id === sid &&
            l.disease_type_id === di,
        ),
      createdLesion = false;
    if (!l) {
      l = {
        id: newId(),
        study_id: study,
        series_id: sid,
        disease_type_id: di,
        tissue_type: di === "MENISCUS_INJURY" ? target : undefined,
        target_key: di === "MENISCUS_INJURY" ? target : "OVERALL",
        attributes_json:
          di === "MENISCUS_INJURY"
            ? {
                半月板类型:
                  target === "MEDIAL_MENISCUS" ? "内侧半月板" : "外侧半月板",
              }
            : {},
      };
      createdLesion = true;
      optimistic("lesions", l);
    }
    // Redrawing an existing lesion on the same image replaces that box in
    // place. Reusing its id prevents a temporary duplicate from remaining in
    // React after the server resolves the natural lesion/image uniqueness.
    let existingBox = drawLesion
      ? s.boxes.find(
          (b) =>
            b.lesion_instance_id === l.id &&
            b.sop_instance_uid === im.id,
        )
      : null;
    let box = {
      id: existingBox?.id || newId(),
      lesion_instance_id: l.id,
      sop_instance_uid: im.id,
      slice_index: idx,
      x_min: Math.min(a.p[0], p[0]),
      y_min: Math.min(a.p[1], p[1]),
      x_max: Math.max(a.p[0], p[0]),
      y_max: Math.max(a.p[1], p[1]),
      image_width: im.width,
      image_height: im.height,
    };
    optimistic("boxes", box);
    lesion(l.id);
    mode("select");
    CB({ ...box, series_id: sid });
    let createdBox;
    try {
      if (createdLesion)
        l = await save("lesions", l, true, null, true, true);
      createdBox = await save("boxes", box, true, null, true, true);
    } catch (error) {
      if (createdLesion) {
        await req("/lesions/" + l.id, "DELETE").catch(() => undefined);
        set((state) => ({
          ...state,
          lesions: state.lesions.filter((x) => x.id !== l.id),
        }));
      }
      throw error;
    }
    CB({ ...createdBox, series_id: sid });
  }
  let source =
    clipboard &&
    clipboard.series_id === sid &&
    clipboard.lesion_instance_id === lid &&
    s.lesions.some((l) => l.id === lid)
      ? s.boxes.find((b) => b.id === clipboard.id)
        ? { ...s.boxes.find((b) => b.id === clipboard.id), series_id: sid }
        : null
      : null;
  let alreadyHere =
    source &&
    s.boxes.some(
      (b) =>
        b.lesion_instance_id === source.lesion_instance_id &&
        b.sop_instance_uid === im?.id,
    );
  let ghost =
    source && im && source.sop_instance_uid !== im.id && !alreadyHere
      ? { ...source, ghost: true }
      : null;
  async function clearSlice() {
    if (editLocked) return;
    let count = s.boxes.filter((b) => b.sop_instance_uid === im?.id).length;
    if (!im || !count || pending || busy) return;
    if (
      !confirm(
        "确定清空当前切片的 " +
          count +
          " 个标注框？\n包含所有病害类型；保留病灶属性和其他切片的框。可通过撤销恢复。",
      )
    )
      return;
    let deleted = s.boxes.filter((b) => b.sop_instance_uid === im.id);
    set((state) => ({
      ...state,
      boxes: state.boxes.filter((b) => b.sop_instance_uid !== im.id),
    }));
    CB(null);
    lesion("");
    V(null);
    drag.current = null;
    try {
      let r = await backgroundRequest(
        req("/slices/" + encodeURIComponent(im.id) + "/boxes", "DELETE"),
      );
      H((h) => [...h, { kind: "boxes", batch: r.deleted }]);
      F([]);
      msg("已清空当前切片的 " + r.count + " 个框");
    } catch (e) {
      set((state) => ({ ...state, boxes: [...state.boxes, ...deleted] }));
      let message = "清空失败：" + String(e);
      if (/404|405|Not Found|Method Not Allowed/.test(String(e)))
        message =
          "当前后端尚未加载清空接口，请重启后端后重试。此次未删除任何框。";
      msg(message);
      alert(message);
    }
  }
  async function deleteSelectedBox() {
    if (editLocked) return;
    let box = s.boxes.find(
      (b) => b.sop_instance_uid === im?.id && b.lesion_instance_id === lid,
    );
    if (!box || pending || busy) return;
    set((state) => ({
      ...state,
      boxes: state.boxes.filter((b) => b.id !== box.id),
    }));
    V(null);
    drag.current = null;
    try {
      await backgroundRequest(req("/boxes/" + box.id, "DELETE"));
      H((h) => [...h, { kind: "boxes", before: box, after: null }]);
      F([]);
      msg("已删除当前切片框，病灶及其他切片框保留");
    } catch (e) {
      set((state) => ({ ...state, boxes: [...state.boxes, box] }));
      msg("删除失败：" + String(e));
    }
  }
  async function pasteSelected() {
    if (editLocked) return;
    if (!ghost || pending || busy) return;
    B(true);
    try {
      let { series_id, ghost: unused, ...box } = ghost;
      await save("boxes", {
        ...box,
        id: newId(),
        sop_instance_uid: im.id,
        slice_index: idx,
        source_box_id: source.id,
      });
      msg("已粘贴：保留原病灶实例、颜色和属性");
    } catch (e) {
      msg("粘贴失败：" + String(e));
    } finally {
      B(false);
    }
  }
  E(() => {
    function keydown(e: KeyboardEvent) {
      let element = e.target as HTMLElement;
      if (
        element?.closest(
          'input,textarea,select,[contenteditable="true"],[role="textbox"]',
        ) ||
        draft ||
        e.isComposing ||
        e.altKey
      )
        return;
      let mod = e.ctrlKey || e.metaKey,
        key = e.key.toLowerCase();
      let run = (action) => {
        e.preventDefault();
        if (e.repeat || pending > 0 || busy) return;
        Promise.resolve()
          .then(action)
          .catch((error) => msg("快捷键操作失败：" + String(error)));
      };
      if (mod && key === "c") {
        run(() => {
          let box = s.boxes.find(
            (b) =>
              b.sop_instance_uid === im?.id && b.lesion_instance_id === lid,
          );
          if (!box) {
            msg("请先选中当前切片的框，再复制");
            return;
          }
          selectBox(box);
          msg("已复制选中框，可切换切片后按 Ctrl+V 粘贴");
        });
        return;
      }
      if (mod && key === "v") {
        if (editLocked) return;
        run(() => {
          if (!ghost) {
            msg(
              alreadyHere
                ? "当前切片已有该病灶框"
                : "请先选中或复制一个框，再切换切片粘贴",
            );
            return;
          }
          return pasteSelected();
        });
        return;
      }
      if (mod && key === "z") {
        if (editLocked) return;
        run(() => undo(e.shiftKey));
        return;
      }
      if (mod && key === "y") {
        if (editLocked) return;
        run(() => undo(true));
        return;
      }
      if (mod && key === "s") {
        if (editLocked) return;
        run(async () => {
          B(true);
          try {
            await commit();
          } finally {
            B(false);
          }
        });
        return;
      }
      if (mod) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        if (images.length)
          slice(
            Math.max(
              0,
              Math.min(
                images.length - 1,
                idx + (e.key === "ArrowRight" ? 1 : -1),
              ),
            ),
          );
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        CB(null);
        lesion("");
        V(null);
        drag.current = null;
        mode("select");
        return;
      }
      if (key === "r") {
        if (editLocked) return;
        run(() => {
          if (im && dis?.box_policy !== "NONE") {
            setDrawLesion("");
            mode("draw");
          }
        });
        return;
      }
      if (key === "v") {
        run(() => mode("select"));
        return;
      }
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });
  async function copy() {
    if (editLocked) return;
    if (!idx) return;
    for (let b of s.boxes.filter(
      (b) =>
        b.sop_instance_uid === images[idx - 1].id &&
        (!lid || b.lesion_instance_id === lid),
    )) {
      if (
        s.boxes.some(
          (x) =>
            x.sop_instance_uid === im.id &&
            x.lesion_instance_id === b.lesion_instance_id,
        )
      )
        continue;
      await save("boxes", {
        ...b,
        id: newId(),
        sop_instance_uid: im.id,
        slice_index: idx,
        source_box_id: b.id,
      });
    }
  }
  async function undo(redo = false) {
    if (editLocked) return;
    let list = redo ? future : history;
    if (!list.length) return;
    let h = list.at(-1);
    if (h.batch) {
      for (let box of h.batch) {
        if (redo) await req("/boxes/" + box.id, "DELETE");
        else await save("boxes", box, false);
      }
      await refresh();
      if (redo) {
        F(list.slice(0, -1));
        H([...history, h]);
      } else {
        H(list.slice(0, -1));
        F([...future, h]);
      }
      return;
    }
    let value = redo ? h.after : h.before;
    if (value) await save(h.kind, value, false);
    else if ((h.after || h.before)?.id) {
      await req(
        "/" + h.kind + "/" + encodeURIComponent((h.after || h.before).id),
        "DELETE",
      );
      await refresh();
    }
    if (redo) {
      F(list.slice(0, -1));
      H([...history, h]);
    } else {
      H(list.slice(0, -1));
      F([...future, h]);
    }
  }
  return (
    <>
      <header>
        <span>
          当前账号：{user.display_name}（
          {reviewSubmission ? (readOnlyReview ? "只读查看" : "审核模式") : "普通用户"}）
        </span>
        <button disabled={pending > 0 || busy} onClick={onLogout}>
          退出登录
        </button>
        <b>Knee MRI Annotation</b>
        <span>{ser?.description || "本地膝关节 MRI 标注"}</span>
        <small>{status}</small>
        <span
          className={
            "sync-status " +
            (syncError
              ? "failed"
              : queued
                ? "queued"
                : pending || syncing
                  ? "saving"
                  : "saved")
          }
          title={syncError || ""}
        >
          {syncError
            ? "保存失败"
            : queued
              ? `待同步 ${queued}`
              : pending || syncing
                ? `同步中 ${pending + syncing}`
                : "已同步"}
        </span>
        {!editLocked && <button
          className="save-action"
          disabled={pending > 0 || busy}
          onClick={async () => {
            B(true);
            try {
              await commit();
            } catch (e) {
              msg("保存失败：" + String(e));
            } finally {
              B(false);
            }
          }}
        >
          {pending ? "正在保存草稿…" : "保存标注"}
        </button>}
        {!reviewSubmission && <button
          className="submit-action"
          disabled={!study || pending > 0 || busy || pendingAnnotatorReview}
          onClick={() =>
            submitReview().catch((e) => msg("提交失败：" + String(e)))
          }
        >
          {pendingAnnotatorReview ? "等待审核中" : "提交审核"}
        </button>}
        {pendingAnnotatorReview && (
          <span className="submission-status read-only">待审核 · 当前检查暂不可修改</span>
        )}
        {readOnlyReview && (
          <span className="submission-status read-only">已审核 · 只读查看</span>
        )}
        {study &&
          (() => {
            let x = submissions.find((x) => x.study_uid === study);
            return x ? (
              <span className={"submission-status " + x.status}>
                {x.status === "SUBMITTED"
                  ? "待审核"
                  : x.status === "APPROVED"
                    ? "已通过"
                    : "已驳回：" + (x.rejection_reason || "")}
              </span>
            ) : null;
          })()}
        {archive && (
          <button
            disabled={busy}
            onClick={async () => {
              B(true);
              try {
                await req("/imported/restore/" + archive, "POST");
                A("");
                await refresh();
                msg("已恢复删除的数据");
              } catch (e) {
                msg(String(e));
              } finally {
                B(false);
              }
            }}
          >
            撤销上次数据删除
          </button>
        )}
        {["json", "csv", "coco"].map((f) => (
          <button
            key={f}
            className="export-action"
            disabled={!sid || pending > 0 || busy}
            onClick={() => exportCurrent(f)}
          >
            导出 {f.toUpperCase()}
          </button>
        ))}
      </header>
      {!localImages.checking &&
        activeStudyId &&
        localImages.total > 0 &&
        localImages.available < localImages.total && (
          <section className="missing-dicom-alert" role="alert">
            <div>
              <b>本机缺少该检查影像，请导入对应 DICOM</b>
              <span>
                Patient ID：<strong>{patientIdHint}</strong>
              </span>
              <small>
                本机已有 {localImages.available}/{localImages.total} 张。影像只保存到当前浏览器，不会上传服务器。
              </small>
            </div>
            <label className="primary-action local-dicom-import">
              导入 DICOM 文件夹
              <input
                type="file"
                multiple
                {...({ webkitdirectory: "" } as any)}
                onChange={(event) => importDicom(event.currentTarget)}
              />
            </label>
            <label className="local-dicom-import">
              导入 DICOM ZIP
              <input
                type="file"
                accept=".zip"
                onChange={(event) => importDicom(event.currentTarget)}
              />
            </label>
          </section>
        )}
      <main>
        <aside>
          <h3>患者与实际序列</h3>
          {!reviewSubmission && <label className="upload">
            选择本地文件夹
            <input
              type="file"
              multiple
              {...({ webkitdirectory: "" } as any)}
              onChange={(event) => importDicom(event.currentTarget)}
            />
          </label>}
          {!reviewSubmission && <label>
            读取本地 ZIP
            <input
              type="file"
              accept=".zip"
              onChange={(event) => importDicom(event.currentTarget)}
            />
          </label>}
          {Array.from(
            new Set<string>(displayedStudies.map((st) => st.patient_id)),
          ).map((patientId) => (
            <div className="patient-group" key={patientId}>
              <div className="patient-group-heading">
                <small>患者</small>
                <b>
                  {s.patients.find((x) => x.id === patientId)?.patient_code ||
                    "编号未记录"}
                </b>
                <span>当前检查</span>
              </div>
              {displayedStudies
                .filter((st) => st.patient_id === patientId)
                .map((st) => (
                  <section
                    key={st.id}
                    className={
                      "study-card" + (study === st.id ? " current-study" : "")
                    }
                  >
                    <div className="study-card-heading">
                      <span>当前检查</span>
                      <small>{st.date || "日期未记录"}</small>
                    </div>
                    <button
                      className="danger-action subtle-danger"
                      disabled={pending > 0 || busy}
                      onClick={() => removeData("studies", st.id)}
                    >
                      删除该影像数据
                    </button>
                    <p className="study-description">
                      {st.description || "未命名检查"}
                    </p>
                    {s.series
                      .filter((x) => x.study_id === st.id)
                      .map((x) => {
                        const recommendation = annotationRecommendation(x);
                        return (
                        <div
                          key={x.id}
                          className={recommendation ? "recommended-series" : ""}
                        >
                          <button
                            className={sid === x.id ? "active" : ""}
                            title={
                              recommendation
                                ? `推荐标注：${recommendation.planeLabel} · ${recommendation.weighting}`
                                : undefined
                            }
                            onClick={() => {
                              if (allowLeave()) {
                                series(x.id);
                                slice(0);
                                if (loadedStudy.current !== x.study_id)
                                  refresh(x.study_id).catch((e) =>
                                    msg(String(e)),
                                  );
                              }
                            }}
                          >
                            <span className="series-title-line">
                              <span>{x.number} · {x.description}</span>
                              {recommendation && (
                                <span className="annotation-required-badge">
                                  需要标注
                                </span>
                              )}
                            </span>
                            <small>
                              {x.orientation} ·{" "}
                              {
                                s.instances.filter((i) => i.series_id === x.id)
                                  .length
                              }{" "}
                              张 ·{" "}
                              {
                                s.boxes.filter((b) =>
                                  s.instances.some(
                                    (i) =>
                                      i.id === b.sop_instance_uid &&
                                      i.series_id === x.id,
                                  ),
                                ).length
                              }{" "}
                              框
                              {seriesFindingLabels(x.id).map((label) => (
                                <React.Fragment key={label}>
                                  {" · "}{label}
                                </React.Fragment>
                              ))}
                            </small>
                          </button>
                        </div>
                      )})}
                    {reviewSubmission && st.id === reviewSubmission.study_uid && (
                      <SubmissionChanges
                        changes={reviewChanges}
                        navigable
                        onNavigate={navigateReviewChange}
                      />
                    )}
                  </section>
                ))}
            </div>
          ))}
        </aside>
        <article>
          <nav>
            {["select", "draw", "window", "pan", "zoom"].map((t) => (
              <button
                disabled={
                  (t === "draw" && (!im || dis?.box_policy === "NONE")) ||
                  (editLocked && t === "draw")
                }
                className={tool === t ? "active" : ""}
                onClick={() => {
                  setDrawLesion("");
                  mode(t);
                }}
              >
                {
                  {
                    select: "选择",
                    draw: "矩形框标注",
                    window: "窗宽窗位",
                    pan: "平移",
                    zoom: "缩放",
                  }[t]
                }
              </button>
            ))}
            <button
              onClick={() => {
                vp.current?.resetCamera();
                vp.current?.resetProperties();
                vp.current?.render();
              }}
            >
              复位
            </button>
            <button disabled={editLocked} title="Ctrl+Z" onClick={() => undo()}>
              撤销
            </button>
            <button disabled={editLocked} title="Ctrl+Y / Ctrl+Shift+Z" onClick={() => undo(true)}>
              重做
            </button>
          </nav>
          <div className="shortcut-help">
            Ctrl+C 复制选中框 · Ctrl+V 粘贴 · Ctrl+Z 撤销 · Ctrl+Y /
            Ctrl+Shift+Z 重做 · Ctrl+S 保存
            <br />← / → 切片 · R 画框 · V 选择 · Esc 取消选择（Mac 使用 ⌘ 代替
            Ctrl）
          </div>
          <div
            className="viewer"
            style={{ cursor: tool === "draw" ? "crosshair" : "default" }}
            ref={el}
            onWheel={(e) =>
              slice(
                Math.max(
                  0,
                  Math.min(images.length - 1, idx + (e.deltaY > 0 ? 1 : -1)),
                ),
              )
            }
            onPointerDown={startPointer}
            onPointerMove={(e) => {
              let d = drag.current;
              if (!d) return;
              if (d.edit) {
                if (Math.hypot(e.clientX - d.x, e.clientY - d.y) < 5) return;
                V(editedBox(d, point(e)));
                return;
              }
              if (tool === "draw") {
                let p = point(e);
                V({
                  x_min: Math.min(d.p[0], p[0]),
                  y_min: Math.min(d.p[1], p[1]),
                  x_max: Math.max(d.p[0], p[0]),
                  y_max: Math.max(d.p[1], p[1]),
                });
                return;
              }
              if (tool === "select") return;
              let dx = e.clientX - d.x,
                dy = e.clientY - d.y;
              if (tool === "window") {
                let v = d.props.voiRange || { lower: 0, upper: 1000 };
                vp.current.setProperties({
                  voiRange: {
                    lower: v.lower + dx - dy,
                    upper: Math.max(v.lower + dx - dy + 1, v.upper + dx + dy),
                  },
                });
              }
              if (tool === "zoom")
                vp.current.setCamera({
                  parallelScale: d.camera.parallelScale * Math.exp(dy / 150),
                });
              if (tool === "pan") {
                let a = vp.current.canvasToWorld([d.x, d.y]),
                  b = vp.current.canvasToWorld([e.clientX, e.clientY]);
                let delta = a.map((v, i) => v - b[i]);
                vp.current.setCamera({
                  focalPoint: d.camera.focalPoint.map((v, i) => v + delta[i]),
                  position: d.camera.position.map((v, i) => v + delta[i]),
                });
              }
              vp.current.render();
            }}
            onPointerUp={(e) => end(e).catch((e) => msg(String(e)))}
          >
            <svg
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                pointerEvents: "none",
                zIndex: 5,
              }}
            >
              {s.boxes
                .filter((b) => b.sop_instance_uid === im?.id)
                .filter((b) => !preview?.id || b.id !== preview.id)
                .map((b) =>
                  rectangle(b, b.id, lesionColor(b.lesion_instance_id)),
                )}
              {ghost &&
                rectangle(
                  ghost,
                  "ghost",
                  lesionColor(ghost.lesion_instance_id),
                )}
              {preview &&
                rectangle(
                  preview,
                  preview.id || "preview",
                  preview.lesion_instance_id
                    ? lesionColor(preview.lesion_instance_id)
                    : "#ffe066",
                )}
            </svg>
            {!im && (
              <div className="empty">
                导入 DICOM 后选择实际序列
                <br />
                影像仅在本地读取 · 标注保存在服务器数据库
              </div>
            )}
          </div>
          <div role="status" style={{ color: "#ffcf7d", padding: 8 }}>
            {imageStatus}
          </div>
          <footer>
            <button onClick={() => slice(Math.max(0, idx - 1))}>上一张</button>
            <input
              type="range"
              min="0"
              max={Math.max(0, images.length - 1)}
              value={idx}
              onChange={(e) => slice(+e.target.value)}
            />
            {images.length ? idx + 1 : 0} / {images.length}
            <button onClick={() => slice(Math.min(images.length - 1, idx + 1))}>
              下一张
            </button>
          </footer>
          {im && (
            <section className="annotation-panel">
              <div className="slice-box-toolbar">
                <b>当前切片框</b>
                <span
                  className="selection-actions"
                  style={{
                    visibility:
                      dis?.box_policy !== "NONE" && (source || selected)
                        ? "visible"
                        : "hidden",
                  }}
                >
                  <button
                    className="primary-action"
                    disabled={editLocked || !ghost || pending > 0 || busy}
                    title="Ctrl+V"
                    onClick={pasteSelected}
                  >
                    {alreadyHere ? "已存在" : "粘贴"}
                  </button>
                  {selected && (
                    <button
                      className="primary-action"
                      disabled={editLocked || !im || pending > 0 || busy}
                      onClick={() => {
                        setDrawLesion(selected.id);
                        mode("draw");
                        imageMsg(
                          "为当前病灶画框：在影像上拖动绘制，共用该病灶的颜色和属性。",
                        );
                      }}
                    >
                      {s.boxes.some(
                        (b) =>
                          b.lesion_instance_id === selected.id &&
                          b.sop_instance_uid === im?.id,
                      )
                        ? "重新绘制当前框"
                        : "为当前病灶画框"}
                    </button>
                  )}
                  <button
                    disabled={!source}
                    onClick={() => {
                      CB(null);
                      lesion("");
                    }}
                  >
                    取消选中
                  </button>
                  <button
                    className="danger-action"
                    disabled={
                      editLocked ||
                      pending > 0 ||
                      busy ||
                      !s.boxes.some(
                        (b) =>
                          b.sop_instance_uid === im?.id &&
                          b.lesion_instance_id === lid,
                      )
                    }
                    onClick={deleteSelectedBox}
                  >
                    删除此框
                  </button>
                </span>
              </div>
              <div className="annotation-list">
                {s.boxes
                  .filter((b) => b.sop_instance_uid === im.id)
                  .map((b) => (
                    <div
                      key={b.id}
                      data-box-id={b.id}
                      className={
                        "slice-box-row" +
                        (b.lesion_instance_id === lid ? " selected" : "")
                      }
                      style={{
                        borderLeftColor: lesionColor(b.lesion_instance_id),
                        background:
                          b.lesion_instance_id === lid
                            ? "color-mix(in srgb, " +
                              lesionColor(b.lesion_instance_id) +
                              " 20%, #111e30)"
                            : undefined,
                      }}
                      onClick={() => selectBox(b)}
                    >
                      <div className="box-card-header">
                        <span
                          style={{ color: lesionColor(b.lesion_instance_id) }}
                        >
                          {b.lesion_instance_id.slice(0, 8)}
                        </span>
                        <small
                          className="selected-label"
                          style={{
                            visibility:
                              b.lesion_instance_id === lid
                                ? "visible"
                                : "hidden",
                          }}
                        >
                          已选中
                        </small>
                        <button
                          className="danger-action subtle-danger"
                          disabled={editLocked || pending > 0 || busy}
                          onClick={async (e) => {
                            e.stopPropagation();
                            set((state) => ({
                              ...state,
                              boxes: state.boxes.filter((x) => x.id !== b.id),
                            }));
                            try {
                              await backgroundRequest(
                                req("/boxes/" + b.id, "DELETE"),
                              );
                              H((h) => [
                                ...h,
                                { kind: "boxes", before: b, after: null },
                              ]);
                              F([]);
                            } catch (error) {
                              set((state) => ({
                                ...state,
                                boxes: [...state.boxes, b],
                              }));
                              msg("删除失败：" + String(error));
                            }
                          }}
                        >
                          删除此框
                        </button>
                      </div>
                      <div className="box-coordinates">
                        {["x_min", "y_min", "x_max", "y_max"].map((k) => (
                          <label key={k} title={k + " = " + b[k]}>
                            {
                              {
                                x_min: "X₁",
                                y_min: "Y₁",
                                x_max: "X₂",
                                y_max: "Y₂",
                              }[k]
                            }
                            <input
                              disabled={editLocked}
                              className="coord"
                              aria-label={k}
                              type="number"
                              step="0.01"
                              value={Number(b[k].toFixed(2))}
                              onChange={(e) =>
                                debounceSave("boxes", {
                                  ...b,
                                  [k]: +e.target.value,
                                })
                              }
                            />
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </section>
          )}
        </article>
        <aside>
          <section className="overall-annotation">
            <h3>统一病害标注</h3>
            <select
              value={di}
              onChange={(e) => {
                if (allowLeave()) {
                  let code = e.target.value;
                  disease(code);
                  lesion("");
                  CB(null);
                  V(null);
                  drag.current = null;
                  mode(
                    s.diseases.find((d) => d.id === code)?.box_policy ===
                      "REQUIRED"
                      ? "draw"
                      : "select",
                  );
                }
              }}
            >
              {s.diseases
                .filter((x) => x.active)
                .map((x) => (
                  <option value={x.id}>{x.disease_name}</option>
                ))}
            </select>
            {study && dis && (
              <>
                {dis.overall_fields.length > 0 && (
                  <div className="overall-fields">
                    {di === "MENISCUS_INJURY" && (
                      <label>
                        半月板侧别
                        <select
                          value={target}
                          onChange={(e) => {
                            T(e.target.value);
                            lesion("");
                            CB(null);
                            mode("select");
                          }}
                        >
                          <option value="">请选择侧别</option>
                          <option value="MEDIAL_MENISCUS">内侧半月板</option>
                          <option value="LATERAL_MENISCUS">外侧半月板</option>
                        </select>
                      </label>
                    )}
                    {(di !== "MENISCUS_INJURY" || target) && (
                      <>
                        {!assessmentReady && (
                          <p>
                            请先为当前病害及侧别绘制病灶框，再填写整体评估。
                          </p>
                        )}
                        <fieldset
                          disabled={editLocked || !assessmentReady}
                          style={{
                            border: 0,
                            padding: 0,
                            margin: 0,
                            opacity: assessmentReady ? 1 : 0.5,
                          }}
                        >
                          {forms(
                            dis.overall_fields,
                            ass?.attributes_json || {},
                            (v) =>
                              debounceSave("assessments", {
                                study_id: study,
                                series_id: sid,
                                disease_type_id: di,
                                target_key:
                                  di === "MENISCUS_INJURY" ? target : di,
                                attributes_json: v,
                              }),
                          )}
                        </fieldset>
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </section>
          {study && dis && (
            <>
              {dis.box_policy !== "NONE" && (
                <section className="lesion-properties">
                  <button
                    disabled={
                      editLocked ||
                      !im ||
                      (di === "MENISCUS_INJURY" && !target)
                    }
                    className={
                      "primary-action " + (tool === "draw" ? "active" : "")
                    }
                    onClick={() => {
                      setDrawLesion("");
                      mode("draw");
                      lesion("");
                      imageMsg("矩形框标注：在影像上按住左键拖动，松开完成。");
                    }}
                  >
                    ＋新增局部病灶{tool === "draw" ? " · 请在影像上拖框" : ""}
                  </button>
                  <div className="lesion-list">
                    {ls
                      .filter(
                        (l) =>
                          l.disease_type_id === di &&
                          l.series_id === sid &&
                          s.boxes.some((b) => b.lesion_instance_id === l.id),
                      )
                      .map((l, index) => (
                        <details
                          key={l.id}
                          className={
                            "lesion-entry" + (lid === l.id ? " selected" : "")
                          }
                          style={{ borderLeftColor: lesionColor(l.id) }}
                          data-lesion-id={l.id}
                          open={expanded === l.id}
                        >
                          <summary
                            onClick={(e) => {
                              e.preventDefault();
                              if (expanded === l.id) {
                                expand("");
                              } else {
                                selectLesionEntry(l);
                                expand(l.id);
                              }
                            }}
                          >
                            <span style={{ color: lesionColor(l.id) }}>
                              病灶 {index + 1} · {l.id.slice(0, 8)}
                            </span>
                            {missing(
                              dis,
                              dis.lesion_fields,
                              l.attributes_json || {},
                            ).length > 0 && (
                              <span
                                className="lesion-incomplete"
                                title={
                                  "缺少：" +
                                  missing(
                                    dis,
                                    dis.lesion_fields,
                                    l.attributes_json || {},
                                  ).join("、")
                                }
                              >
                                未完成
                              </span>
                            )}
                            <small>
                              {
                                s.boxes.filter(
                                  (b) => b.lesion_instance_id === l.id,
                                ).length
                              }{" "}
                              个切片框
                            </small>
                          </summary>
                          <button
                            onClick={() => selectLesionEntry(l)}
                            title="跳转到该病灶最近选中的切片框"
                          >
                            定位病灶
                          </button>
                          {forms(
                            dis.lesion_fields.filter(
                              (f) =>
                                di !== "MENISCUS_INJURY" ||
                                f.field_code !== "半月板类型",
                            ),
                            l.attributes_json || {},
                            (v) =>
                              debounceSave("lesions", {
                                ...l,
                                attributes_json: v,
                              }),
                          )}
                          <button
                            className="danger-action"
                            disabled={editLocked}
                            onClick={async () => {
                              if (
                                confirm(
                                  "确定删除该病灶及其所有切片上的标注框和局部属性？",
                                )
                              ) {
                                let removedBoxes = s.boxes.filter(
                                  (b) => b.lesion_instance_id === l.id,
                                );
                                set((state) => ({
                                  ...state,
                                  lesions: state.lesions.filter(
                                    (x) => x.id !== l.id,
                                  ),
                                  boxes: state.boxes.filter(
                                    (b) => b.lesion_instance_id !== l.id,
                                  ),
                                }));
                                if (lid === l.id) lesion("");
                                try {
                                  await backgroundRequest(
                                    req("/lesions/" + l.id, "DELETE"),
                                  );
                                } catch (error) {
                                  set((state) => ({
                                    ...state,
                                    lesions: [...state.lesions, l],
                                    boxes: [...state.boxes, ...removedBoxes],
                                  }));
                                  msg("删除失败：" + String(error));
                                }
                              }
                            }}
                          >
                            删除该病灶（所有切片）
                          </button>
                        </details>
                      ))}
                  </div>
                </section>
              )}
            </>
          )}
          {im && (
            <button
              className="danger-action"
              disabled={
                editLocked ||
                pending > 0 ||
                busy ||
                !s.boxes.some((b) => b.sop_instance_uid === im.id)
              }
              onClick={clearSlice}
            >
              清空当前切片标注框
            </button>
          )}
          {study && currentIssues.length > 0 && (
            <details
              className="issue-summary"
              open={issueOpen}
              onToggle={(e) => IO(e.currentTarget.open)}
            >
              <summary>
                当前检查有 {currentIssues.length} 项未完成（点击查看）
              </summary>
              {currentIssues.map((item, i) => (
                <button key={i} onClick={() => locateIssue(item)}>
                  {item.label}：{item.missing.join("、")}
                </button>
              ))}
            </details>
          )}
        </aside>
      </main>
      {draft && (
        <div className="modal">
          <section>
            <h2>配置病害</h2>
            <label>
              中文名称
              <input
                value={draft.disease_name}
                onChange={(e) => D({ ...draft, disease_name: e.target.value })}
              />
            </label>
            <label>
              唯一编码
              <input
                value={draft.disease_code}
                onChange={(e) => D({ ...draft, disease_code: e.target.value })}
              />
            </label>
            <select
              value={draft.box_policy}
              onChange={(e) => D({ ...draft, box_policy: e.target.value })}
            >
              <option>NONE</option>
              <option>OPTIONAL</option>
              <option>REQUIRED</option>
            </select>
            {["overall_fields", "lesion_fields"].map((k) => (
              <label>
                {k === "overall_fields" ? "整体属性" : "局部属性"}（JSON 配置）
                <textarea
                  defaultValue="[]"
                  onChange={(e) => {
                    try {
                      D({ ...draft, [k]: JSON.parse(e.target.value) });
                    } catch {
                      msg("字段 JSON 尚未有效");
                    }
                  }}
                />
                <small>
                  字段：field_code、field_name、field_type、options。类型支持
                  single_select / multi_select / text / number / boolean
                </small>
              </label>
            ))}
            <button
              onClick={async () => {
                if (!draft.disease_code || !draft.disease_name) return;
                await save("diseases", {
                  ...draft,
                  id: draft.disease_code,
                  active: true,
                });
                D(null);
              }}
            >
              保存并立即启用
            </button>
            <button onClick={() => D(null)}>取消</button>
          </section>
        </div>
      )}
    </>
  );
}
function SubmissionChanges({ changes, navigable = false, onNavigate = null }) {
  if (!changes?.available)
    return <p className="revision-changes unavailable">修改对比：{changes?.reason || "暂无历史快照"}</p>;
  if (changes.first)
    return <p className="revision-changes first">首次提交，没有上一版本可比较</p>;
  let normalized = (item: any) => String(item.label || "修改项")
      .replace(/第\s*(\d+)\s*张框/g, "第 $1 个切片"),
    baseLabel = (item: any) => normalized(item)
      .replace(/ · 第 .* 个切片$/, "")
      .replace(/ · 病灶属性$/, ""),
    group = (items: any[], changeType: string) => {
      let grouped = new Map<string, { common: any[]; slices: Map<string, any[]> }>();
      for (let item of items) {
        let label = normalized(item),
          base = baseLabel(item),
          instanceKey = item.lesion_id || `${item.kind}:${item.disease_code || base}`,
          key = `${item.series_uid || base}|${instanceKey}`,
          bucket = grouped.get(key) || { common: [], slices: new Map<string, any[]>() },
          sliceKey = String(item.sop_instance_uid || item.slice_index || label.match(/第\s*(\d+)\s*个切片/)?.[1] || "");
        if (sliceKey) bucket.slices.set(sliceKey, [...(bucket.slices.get(sliceKey) || []), item]);
        else bucket.common.push(item);
        grouped.set(key, bucket);
      }
      let combined: any[][] = [];
      for (let bucket of grouped.values()) {
        let sliceGroups = Array.from(bucket.slices.values());
        if (sliceGroups.length) {
          sliceGroups[0] = [...bucket.common, ...sliceGroups[0]];
          combined.push(...sliceGroups);
        } else combined.push(bucket.common);
      }
      return combined.map((members) => {
        let preferred = members.find((x) => x.kind === "box") ||
            members.find((x) => x.kind === "lesion") || members[0],
          base = baseLabel(members[0]),
          details = Array.from(new Set(members.map((item) =>
            item.kind === "assessment" ? "整体属性" :
              item.kind === "lesion" ? "病灶属性" :
                normalized(item).split(" · ").at(-1) || "标注框"
          )));
        return { ...preferred, _changeType: changeType, label: `${base} · ${details.join("、")}` };
      });
    },
    groupedChanges = {
      added: group(changes.added, "added"),
      modified: group(changes.modified, "modified"),
      deleted: group(changes.deleted, "deleted"),
    },
    total = groupedChanges.added.length + groupedChanges.modified.length + groupedChanges.deleted.length;
  return (
    <details className="revision-changes" open={total > 0}>
      <summary>
        相对上次提交：新增 {groupedChanges.added.length} 项，修改 {groupedChanges.modified.length} 项，删除 {groupedChanges.deleted.length} 项
      </summary>
      {!total && <p>标注内容没有变化</p>}
      {[["新增", groupedChanges.added], ["修改", groupedChanges.modified], ["删除", groupedChanges.deleted]].map(([title, items]: any) =>
        !!items.length && <div key={title}><b>{title}</b><ul>{items.map((item) =>
          <li key={`${item.kind}:${item.lesion_id || item.box_id || ""}:${item.label}`}>
            {navigable ? <button className="revision-change-link" onClick={() => onNavigate?.(item)}>{item.label}</button> : item.label}
          </li>
        )}</ul></div>
      )}
    </details>
  );
}
function ImageReviewDashboard({ user, onLogout, admin = false }) {
  const [items, setItems] = S<any[]>([]),
    [selected, setSelected] = S<any>(null),
    [error, setError] = S(""),
    [accounts, setAccounts] = S(false),
    [reviewFilter, setReviewFilter] = S<"ALL" | "REVIEWED" | "PENDING">("ALL");
  async function load() {
    try {
      let result = await workflowRequest("/submissions");
      setItems(result.submissions || []);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  E(() => {
    load();
    let timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);
  async function finish(action) {
    if (selected)
      window.dispatchEvent(
        new CustomEvent("review-decision", { detail: action }),
      );
  }
  if (accounts)
    return (
      <div>
        <button className="management-back" onClick={() => setAccounts(false)}>
          ← 返回影像审核
        </button>
        <ReviewDashboard user={user} onLogout={onLogout} admin />
      </div>
    );
  if (selected)
    {
      const canReview = selected.status === "SUBMITTED";
    return (
      <div className="review-workspace">
        <div className="review-actionbar">
          <b>
            {canReview ? "正在审核：" : "只读查看："}
            {selected.study_description || selected.study_uid}
          </b>
          <span>
            提交人：{selected.submitter_name} · 修订 {selected.revision}
          </span>
          {canReview ? (
            <>
              <button className="approve-action" onClick={() => finish("approve")}>
                审核通过
              </button>
              <button className="danger-action" onClick={() => finish("reject")}>
                驳回并备注
              </button>
            </>
          ) : (
            <span className="submission-status read-only">
              {selected.status === "APPROVED" ? "已通过" : "已驳回"} · 只读
            </span>
          )}
          <button onClick={() => setSelected(null)}>返回审核列表</button>
        </div>
        <App
          user={user}
          onLogout={onLogout}
          reviewSubmission={selected}
          reviewChanges={selected.revision_changes}
          onReviewed={async () => {
            setSelected(null);
            await load();
          }}
        />
      </div>
    );
    }
  const pendingCount = items.filter((item) => item.status === "SUBMITTED").length,
    reviewedCount = items.length - pendingCount,
    visibleItems = items.filter((item) =>
      reviewFilter === "ALL"
        ? true
        : reviewFilter === "PENDING"
          ? item.status === "SUBMITTED"
          : item.status !== "SUBMITTED",
    );
  return (
    <div className="management-shell">
      <header>
        <b>Knee MRI Annotation</b>
        <span>
          {user.display_name}（{admin ? "管理员" : "审核人员"}）
        </span>
        <small>
          {error ||
            `待审核 ${items.filter((x) => x.status === "SUBMITTED").length} 项`}
        </small>
        {admin && <button onClick={() => setAccounts(true)}>账号管理</button>}
        <button onClick={onLogout}>退出登录</button>
      </header>
      <section className="image-review-list">
        <h2>影像标注审核</h2>
        <p>
          待审核项目可进入影像界面查看和修改；已通过、已驳回项目仍可进入查看，但不能修改或再次审核。
        </p>
        <div className="review-filters" role="group" aria-label="审核状态筛选">
          {[
            ["ALL", "全部", items.length],
            ["REVIEWED", "已审核", reviewedCount],
            ["PENDING", "未审核", pendingCount],
          ].map(([value, label, count]) => (
            <button
              key={value}
              className={reviewFilter === value ? "active" : ""}
              aria-pressed={reviewFilter === value}
              onClick={() => setReviewFilter(value as "ALL" | "REVIEWED" | "PENDING")}
            >
              {label} <span>{count}</span>
            </button>
          ))}
        </div>
        {!visibleItems.length && (
          <p className="review-empty">当前筛选条件下没有审核记录。</p>
        )}
        {visibleItems.map((item) => (
          <article className="review-card" key={item.id}>
            <div>
              <b>{item.study_description || item.study_uid}</b>
              <span className={"submission-status " + item.status}>
                {item.status === "SUBMITTED"
                  ? "待审核"
                  : item.status === "APPROVED"
                    ? "已通过"
                    : "已驳回"}
              </span>
            </div>
            <p>
              提交人：{item.submitter_name} · 修订 {item.revision} · 最近更新{" "}
              {new Date(item.updated_at || item.submitted_at).toLocaleString()}
            </p>
            {item.rejection_reason && (
              <p className="reject-reason">驳回理由：{item.rejection_reason}</p>
            )}
            <SubmissionChanges changes={item.revision_changes} />
            <button
              className="primary-action open-review"
              onClick={() => setSelected(item)}
            >
              {item.status === "SUBMITTED" ? "进入影像审核" : "查看审核记录"}
            </button>
          </article>
        ))}
      </section>
    </div>
  );
}
function api(path, method = "GET", body?: any) {
  return fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(async (r) => {
    let result = await r.json().catch(() => ({}));
    if (!r.ok)
      throw Error(result.detail?.message || result.detail || "请求失败");
    return result;
  });
}
function ReviewDashboard({ user, onLogout, admin = false }) {
  let [items, setItems] = S<any[]>([]),
    [state, setState] = S<any>({
      series: [],
      assessments: [],
      lesions: [],
      boxes: [],
      diseases: [],
    }),
    [error, setError] = S(""),
    [users, setUsers] = S<any[]>([]),
    [form, setForm] = S<any>({
      username: "",
      display_name: "",
      password: "",
      role: "ANNOTATOR",
    });
  async function load() {
    try {
      let [a, b] = await Promise.all([
        workflowRequest("/submissions"),
        req("/state"),
      ]);
      setItems(a.submissions);
      setState(b);
      if (admin) setUsers((await api("/api/admin/users")).users);
    } catch (e) {
      setError(String(e));
    }
  }
  E(() => {
    load();
  }, []);
  async function review(item, action) {
    let reason = "";
    if (action === "reject") {
      reason = prompt("请输入驳回理由") || "";
      if (!reason) return;
    }
    try {
      await workflowRequest("/submissions/" + item.id + "/review", "POST", {
        action,
        reason,
      });
      await load();
    } catch (e) {
      alert(String(e));
    }
  }
  async function create(e) {
    e.preventDefault();
    try {
      await api("/api/admin/users", "POST", form);
      setForm({
        username: "",
        display_name: "",
        password: "",
        role: "ANNOTATOR",
      });
      await load();
    } catch (e) {
      alert(String(e));
    }
  }
  async function edit(u, values) {
    try {
      await api("/api/admin/users/" + u.id, "PUT", values);
      await load();
    } catch (e) {
      alert(String(e));
    }
  }
  let pending = items.filter((x) => x.status === "SUBMITTED");
  return (
    <div className="management-shell">
      <header>
        <b>Knee MRI Annotation</b>
        <span>
          {user.display_name}（{admin ? "管理员" : "审核人员"}）
        </span>
        <small>{error || `待审核 ${pending.length} 项`}</small>
        <button onClick={onLogout}>退出登录</button>
      </header>
      <div className="management-grid">
        <section className="review-panel">
          <h2>标注审核</h2>
          {!items.length && <p>暂无提交记录</p>}
          {items.map((item) => {
            let series = state.series.filter(
              (x) => x.study_id === item.study_uid,
            );
            return (
              <article className="review-card" key={item.id}>
                <div>
                  <b>{item.study_description || item.study_uid}</b>
                  <span className={"submission-status " + item.status}>
                    {item.status === "SUBMITTED"
                      ? "待审核"
                      : item.status === "APPROVED"
                        ? "已通过"
                        : "已驳回"}
                  </span>
                </div>
                <p>
                  提交人：{item.submitter_name} · 修订 {item.revision} ·{" "}
                  {new Date(item.submitted_at).toLocaleString()}
                </p>
                {item.rejection_reason && (
                  <p className="reject-reason">
                    驳回理由：{item.rejection_reason}
                  </p>
                )}
                <details>
                  <summary>查看三个序列及标注属性</summary>
                  {series.map((se) => {
                    let assessments = state.assessments.filter(
                        (x) => x.series_id === se.id,
                      ),
                      lesions = state.lesions.filter(
                        (x) =>
                          x.series_id === se.id &&
                          state.boxes.some(
                            (b) => b.lesion_instance_id === x.id,
                          ),
                      );
                    return (
                      <div className="review-series" key={se.id}>
                        <b>
                          {se.number} · {se.description}
                        </b>
                        <small>
                          {assessments.length} 项整体评价 · {lesions.length}{" "}
                          个病灶 ·{" "}
                          {
                            state.boxes.filter((b) =>
                              state.instances?.some(
                                (i) =>
                                  i.series_id === se.id &&
                                  i.id === b.sop_instance_uid,
                              ),
                            ).length
                          }{" "}
                          个框
                        </small>
                        {assessments.map((a) => (
                          <pre key={a.id}>
                            {
                              state.diseases.find(
                                (d) => d.id === a.disease_type_id,
                              )?.disease_name
                            }
                            ：{JSON.stringify(a.attributes_json, null, 2)}
                          </pre>
                        ))}
                        {lesions.map((l) => (
                          <pre key={l.id}>
                            {
                              state.diseases.find(
                                (d) => d.id === l.disease_type_id,
                              )?.disease_name
                            }
                            局部：{JSON.stringify(l.attributes_json, null, 2)}
                          </pre>
                        ))}
                      </div>
                    );
                  })}
                </details>
                {item.status === "SUBMITTED" && (
                  <div className="review-actions">
                    <button
                      className="save-action"
                      onClick={() => review(item, "approve")}
                    >
                      审核通过
                    </button>
                    <button
                      className="danger-action"
                      onClick={() => review(item, "reject")}
                    >
                      驳回并备注
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </section>
        {admin && (
          <section className="admin-panel">
            <h2>账号管理</h2>
            <form onSubmit={create}>
              <input
                required
                pattern="[A-Za-z0-9]+"
                placeholder="账号"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
              <input
                required
                placeholder="姓名或工号"
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
              />
              <input
                required
                type="password"
                pattern="[A-Za-z0-9]+"
                placeholder="初始密码"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="ANNOTATOR">普通用户</option>
                <option value="REVIEWER">审核人员</option>
                <option value="ADMIN">管理员</option>
              </select>
              <button className="primary-action">新增账号</button>
            </form>
            <div className="user-list">
              {users.map((u) => (
                <div className="user-row" key={u.id}>
                  <div>
                    <b>{u.display_name}</b>
                    <small>
                      {u.username} · {u.active ? "有效" : "已停用"}
                    </small>
                  </div>
                  <select
                    value={u.role}
                    disabled={u.id === user.id}
                    onChange={(e) => edit(u, { role: e.target.value })}
                  >
                    <option value="ANNOTATOR">普通用户</option>
                    <option value="REVIEWER">审核人员</option>
                    <option value="ADMIN">管理员</option>
                  </select>
                  <button
                    onClick={() => {
                      let password = prompt("输入新密码");
                      if (password) edit(u, { password });
                    }}
                  >
                    重置密码
                  </button>
                  <button
                    className="danger-action"
                    disabled={u.id === user.id}
                    onClick={() =>
                      confirm("确定停用该账号？") &&
                      api("/api/admin/users/" + u.id, "DELETE")
                        .then(load)
                        .catch((e) => alert(String(e)))
                    }
                  >
                    {u.active ? "停用" : "已停用"}
                  </button>
                  {!u.active && (
                    <button onClick={() => edit(u, { active: true })}>
                      恢复
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<AuthRoot />);
function AuthRoot() {
  const [user, setUser] = S<any>(null),
    [checking, setChecking] = S(true),
    [username, setUsername] = S(""),
    [password, setPassword] = S(""),
    [error, setError] = S(""),
    [submitting, setSubmitting] = S(false);
  E(() => {
    let active = true;
    fetch("/api/auth/me", { cache: "no-store" })
      .then(async (r) => {
        if (r.ok) {
          let result = await r.json();
          if (active) setUser(result.user);
        } else if (r.status !== 401)
          throw Error("服务器连接失败（HTTP " + r.status + "）");
      })
      .catch((e) => {
        if (active) setError(String(e));
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    let expired = () => {
      setUser(null);
      setError("登录已过期，请重新登录");
    };
    window.addEventListener("auth-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("auth-expired", expired);
    };
  }, []);
  async function submit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      let r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      let result = await r.json();
      if (!r.ok) throw Error(result.detail || "请求失败");
      setPassword("");
      setUser(result.user);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setSubmitting(false);
    }
  }
  async function logout() {
    setSubmitting(true);
    try {
      let r = await fetch("/api/auth/logout", { method: "POST" });
      if (!r.ok) throw Error("退出失败，请重试");
      setUser(null);
      setPassword("");
      setError("");
    } catch (e) {
      alert(String(e));
    } finally {
      setSubmitting(false);
    }
  }
  if (checking)
    return (
      <div className="auth-shell">
        <p>正在检查登录状态…</p>
      </div>
    );
  if (user?.role === "ADMIN")
    return <ImageReviewDashboard user={user} onLogout={logout} admin />;
  if (user?.role === "REVIEWER")
    return <ImageReviewDashboard user={user} onLogout={logout} />;
  if (user) return <App user={user} onLogout={logout} />;
  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <h1>Knee MRI Annotation</h1>
        <p>膝关节 MRI 共享标注平台</p>
        <h2>登录</h2>
        <label>
          账号
          <input
            required
            minLength={1}
            maxLength={64}
            pattern="[A-Za-z0-9]+"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入字母或数字"
          />
        </label>
        <label>
          密码
          <input
            required
            type="password"
            minLength={1}
            maxLength={128}
            pattern="[A-Za-z0-9]+"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入字母或数字"
          />
        </label>
        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}
        <button className="primary-action" disabled={submitting} type="submit">
          {submitting ? "正在登录…" : "登录"}
        </button>
        <small>账号由管理员统一创建和管理。</small>
      </form>
    </div>
  );
}
