#!/usr/bin/env python3
"""
在 docs.json 五语「开发文档 → 服务端 API」tab 注册「考勤」分组（插在 AI 表格之后），
结构与官方菜单一致，已剔除纯血版不支持的页（考勤机管理 / 封账规则）。

OA 审批：文件已入库但暂不开放，默认不注册；开放时加 --include-oa 插在考勤之后。

幂等：目标分组已存在则跳过。docs.json 经 json.load/dump(indent=2) 可逐字节还原，故整体回写不产生无关 diff。

用法：
  python3 scripts/register_open_attendance_navigation.py --dry-run
  python3 scripts/register_open_attendance_navigation.py [--include-oa]
"""
import argparse
import json
import sys
from pathlib import Path

DOCS_JSON = Path(__file__).resolve().parents[1] / "docs.json"

# docs.json 语言块 code → 页面路径前缀（ms 以 uz 注册，目录仍是 ms/）
PATH_PREFIX = {"en": "", "zh": "zh/", "ja": "ja/", "id": "id/", "uz": "ms/"}
LANG_INDEX = {"en": 0, "zh": 1, "ja": 2, "id": 3, "uz": 4}

# 分组名：zh → (en, zh, ja, id, ms)
LABELS = {
    "考勤": ("Attendance", "考勤", "勤怠", "Absensi", "Kehadiran"),
    "OA 审批": ("OA Approval", "OA 审批", "OA 承認", "Persetujuan OA", "Kelulusan OA"),
    "使用教程": ("Tutorials", "使用教程", "チュートリアル", "Tutorial", "Tutorial"),
    "考勤组管理": ("Attendance groups", "考勤组管理", "勤怠グループ管理", "Manajemen grup absensi", "Pengurusan kumpulan kehadiran"),
    "考勤打卡": ("Clock-in", "考勤打卡", "打刻", "Absen", "Daftar masuk"),
    "考勤班次": ("Shifts", "考勤班次", "シフト", "Shift", "Syif"),
    "考勤排班": ("Scheduling", "考勤排班", "シフト設定", "Penjadwalan shift", "Penjadualan syif"),
    "考勤规则": ("Attendance rules", "考勤规则", "勤怠ルール", "Aturan absensi", "Peraturan kehadiran"),
    "考勤统计": ("Attendance statistics", "考勤统计", "勤怠統計", "Statistik kehadiran", "Statistik kehadiran"),
    "假勤审批": ("Leave and attendance approvals", "假勤审批", "休暇・勤怠承認", "Persetujuan cuti dan absensi", "Kelulusan cuti dan kehadiran"),
    "假期管理": ("Leave management", "假期管理", "休暇管理", "Manajemen cuti", "Pengurusan cuti"),
    "官方 OA 审批": ("Official OA Approval", "官方 OA 审批", "公式 OA 承認", "Persetujuan OA resmi", "Kelulusan OA rasmi"),
    "自有 OA 审批": ("Self-built OA Approval", "自有 OA 审批", "自社 OA 承認", "Persetujuan OA mandiri", "Kelulusan OA sendiri"),
    "审批表单": ("Approval forms", "审批表单", "承認フォーム", "Formulir persetujuan", "Borang kelulusan"),
    "审批实例": ("Approval instances", "审批实例", "承認インスタンス", "Instans persetujuan", "Instans kelulusan"),
    "审批钉盘空间&附件": ("Approval Drive space & attachments", "审批钉盘空间&附件", "承認用ドライブスペースと添付ファイル", "Ruang Drive & lampiran persetujuan", "Ruang Drive & lampiran kelulusan"),
    "审批任务": ("Approval tasks", "审批任务", "承認タスク", "Tugas persetujuan", "Tugasan kelulusan"),
    "流程中心任务": ("Process Center tasks", "流程中心任务", "プロセスセンタータスク", "Tugas Pusat Proses", "Tugasan Pusat Proses"),
}

ATTENDANCE = ("考勤", "user-clock", [
    "attendance-overview",
    ("使用教程", [
        "operation-related-to-attendance-group",
        "attendance-group-member-operations",
        "the-replenishment-card-of-enterprise-self-developed-attendance-system-is-synchronized",
        "the-enterprise-big-screen-displays-the-attendance-of-employees",
        "obtain-the-employee-attendance-report-information",
        "enterprise-s-own-oa-approval-system-synchronized-to-dingtalk-during-holidays",
        "attendance-synchronizes-information",
    ]),
    ("考勤组管理", [
        "attendance-group-write",
        "attendance-group-update-interface",
        "delete-attendance-group",
        "attendance-group-search",
        "query-a-single-attendance-group",
        "queries-attendance-group-information-by-id",
        "convert-groupkey-to-groupid",
        "groupid-to-groupkey",
        "batch-query-of-simple-information-of-the-attendance-group",
        "batch-obtain-attendance-group-details",
        "queries-a-user-attendance-group",
        "batch-add-employees-under-the-attendance-group",
        "attendance-group-member-update",
        "batch-query-of-attendance-group-members",
        "query-attendance-group-personnel-information-in-batches",
        "batch-delete-employees-under-the-attendance-group",
        "batch-query-of-employees-in-the-attendance-group",
        "query-members-by-id",
        "batch-add-wifi-under-attendance-group",
        "batch-remove-wifi-under-attendance-group",
        "batch-query-wifi-under-attendance-group",
        "atch-add-position-under-attendance-group",
        "delete-position-in-batches-under-the-attendance-group",
        "batch-query-position-under-attendance-group",
        "attendance-writing-operation-is-brand-new-query",
    ]),
    ("考勤打卡", [
        "open-attendance-clock-in-data",
        "attendance-clock-in-record-is-open",
        "upload-punch-records",
    ]),
    ("考勤班次", [
        "create-modify-shifts",
        "delete-shift",
        "modify-card-settings",
        "query-history-shifts",
        "search-shifts-by-rank",
        "enterprise-shift-query-in-batches",
        "shift-query",
    ]),
    ("考勤排班", [
        "query-scheduling-for-a-day",
        "query-batch-scheduling-information",
        "scheduling-system-attendance-group-scheduling",
        "query-the-results-of-a-batch-of-tasks",
        "interface-for-daily-full-query-of-attendance-scheduling-information",
        "query-scheduling-summary-information",
        "synchronization-scheduling-information",
    ]),
    ("考勤规则", [
        "retrieve-a-list-of-overtime-rules-by-page",
        "retrieve-a-list-of-replenishment-rules-by-page",
        "batch-retrieve-overtime-rules",
    ]),
    ("考勤统计", [
        "determine-whether-to-enable-attendance-intelligent-report",
        "obtain-the-attendance-update-data",
        "obtains-the-holiday-data-from-the-smart-attendance-report",
        "queries-the-enterprise-attendance-report-column",
        "queries-the-column-value-of-the-attendance-report",
    ]),
    ("假勤审批", [
        "api-calculateduration",
        "api-processapprovefinish",
        "notify-the-attendance-to-modify-the-punch-result-when-the",
        "make-up-the-card-after-approval",
        "shift-change-operation-after-approval",
        "calculate-leave-duration",
        "query-status",
    ]),
    ("假期管理", [
        "holiday-management-describe",
        "add-holiday-rules",
        "update-holiday-rules",
        "api-for-deleting-holiday-types",
        "initialize-holiday-balance",
        "bulk-update-holiday-balance",
        "holiday-type-query",
        "query-holiday-balance",
        "batch-query-employee-leave-balance-change-record",
        "obtain-user-attendance-and-holiday-information",
    ]),
    "attendance-interface-common-problems",
])

OA_APPROVAL = ("OA 审批", "stamp", [
    "workflow-overview",
    "oa-formcomponent-message",
    ("使用教程", [
        "use-three-party-process-and-page-docking",
        "use-the-dingtalk-oa-approval-process-and-page-interface",
        "new-version-of-initiate-and-cancel-approval-flow",
        "comment-and-revoke-approval-flow",
        "approve-or-reject-the-new-version",
        "new-version-of-attachment-approval-process",
        "user-form-and-approval-form-query",
    ]),
    ("官方 OA 审批", [
        ("审批表单", [
            "create-an-approval-form-template",
            "obtain-the-form-schema",
            "approval-process-prediction",
            "obtains-a-list-of-approval-forms-visible-to-the-specified",
            "get-all-manageable-forms-for-the-current-enterprise",
            "query-form-components-that-have-been-set-as-criteria-1",
        ]),
        ("审批实例", [
            "create-an-approval-instance",
            "obtains-the-details-of-a-single-approval-instance-pop",
            "revoke-an-approval-instance",
            "official-approval-adds-approval-comments",
            "obtain-an-approval-list-of-instance-ids",
        ]),
        ("审批钉盘空间&附件", [
            "obtains-the-information-about-approval-nail-disk",
            "official-authorized-preview-approval-attachment",
            "download-the-approval-nail-file",
            "download-an-approval-attachment",
        ]),
        ("审批任务", [
            "approve-or-reject-the-approval-task",
            "transfer-the-oa-approval-task",
            "queries-the-number-of-requests-to-be-approved-by-users",
        ]),
    ]),
    ("自有 OA 审批", [
        "oa-access-process",
        ("审批表单", [
            "create-orupdate-the-approval-template-new",
            "obtain-the-template-code",
            "self-owned-approval-deletion-template",
        ]),
        ("审批实例", [
            "create-a-ticket-approval-instance",
            "update-instance-status",
            "self-owned-batch-update-of-instance-status",
        ]),
        ("流程中心任务", [
            "create-pending-tasks-in-process-center",
            "query-oa-approval-tasks-integrated-through-process-center",
            "update-process-center-task-status",
            "cancel-multiple-oa-approval-tasks",
            "clear-oa-approval-data",
        ]),
    ]),
    "common-questions-about-official-oa-approval",
])


def build(items: list, lang: str) -> list:
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(f"{PATH_PREFIX[lang]}open/development/{it}")
        else:
            out.append({"group": LABELS[it[0]][LANG_INDEX[lang]], "pages": build(it[1], lang)})
    return out


def make_group(spec: tuple, lang: str) -> dict:
    name, icon, items = spec
    return {"group": LABELS[name][LANG_INDEX[lang]], "icon": icon, "pages": build(items, lang)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-oa", action="store_true", help="同时注册 OA 审批分组（默认隐藏）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    specs = [ATTENDANCE] + ([OA_APPROVAL] if args.include_oa else [])
    for block in data["navigation"]["languages"]:
        lang = block["language"]
        groups = block["products"][1]["tabs"][1]["groups"]
        anchor = next(i for i, g in enumerate(groups) if g.get("icon") == "table")  # AI 表格
        for offset, spec in enumerate(specs, 1):
            new = make_group(spec, lang)
            if any(g["group"] == new["group"] for g in groups):
                print(f"{lang}: {new['group']} 已存在，跳过")
                continue
            missing = [p for p in json.dumps(new["pages"]).split('"')
                       if "open/development/" in p and not (DOCS_JSON.parent / f"{p}.mdx").exists()]
            if missing:
                print(f"ERROR {lang}: {len(missing)} 页文件不存在，如 {missing[:3]}", file=sys.stderr)
                return 1
            groups.insert(anchor + offset, new)
            print(f"{lang}: 插入 {new['group']}（{json.dumps(new).count('open/development/')} 页）于 {groups[anchor]['group']} 之后")
    if not args.dry_run:
        DOCS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
