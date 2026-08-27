"""Generates the 4 sample ESG report PDFs used as the prototype external
evidence corpus (Phase 10 sections 9-10, 40-41).

Every company/figure here is CLEARLY FICTIONAL, generated for exercising
the pipeline mechanics -- never real-world company facts (section 28/47).
Run once to (re)populate `data/reports/company_{1..4}/`:

    python -m scripts.generate_sample_reports
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"


def _build_pdf(path: Path, pages: list[list[str]]) -> None:
    doc = fitz.open()
    for paragraphs in pages:
        page = doc.new_page(width=612, height=792)
        y = 72.0
        for paragraph in paragraphs:
            page.insert_text((72, y), paragraph, fontsize=11)
            line_count = paragraph.count("\n") + 1
            y += line_count * 14 + 20
    doc.save(str(path))
    doc.close()


# Four clearly fictional companies spanning different ESG emphases, report
# years, and category mixes -- so retrieval/verification can be exercised
# across a real multi-company, multi-year corpus instead of one hardcoded
# company (section 10).
_REPORTS: dict[str, dict] = {
    "company_1": {
        "company": "Aurora Materials Inc. (fictional, synthetic sample data)",
        "report_year": 2024,
        "report_title": "Aurora Materials Inc. 2024 Environmental Report (synthetic sample)",
        "header": "Aurora Materials Inc. | 2024 Environmental Report (SYNTHETIC SAMPLE DATA)",
        "pages": [
            ["Introduction",
             "This report summarizes Aurora Materials' 2024 environmental performance.\n"
             "All figures in this document are synthetic sample data for demonstration purposes."],
            ["Emissions", "Climate",
             "Scope 1 emissions decreased by 15% from the 2021 baseline.\n"
             "Scope 2 emissions were 62,000 tCO2e in 2024."],
            ["Energy", "Renewable Energy",
             "Renewable electricity accounted for 40% of total energy consumption in 2024.\n"
             "The company targets 60% renewable electricity by 2030."],
            ["Water", "Water Management",
             "Total water withdrawal decreased by 8% compared to 2023.\n"
             "Water recycling programs were expanded to two additional facilities."],
        ],
    },
    "company_2": {
        "company": "Meridian Foods Co. (fictional, synthetic sample data)",
        "report_year": 2025,
        "report_title": "Meridian Foods Co. 2025 Sustainability Report (synthetic sample)",
        "header": "Meridian Foods Co. | 2025 Sustainability Report (SYNTHETIC SAMPLE DATA)",
        "pages": [
            ["Introduction",
             "This report summarizes Meridian Foods' 2025 social and environmental performance.\n"
             "All figures in this document are synthetic sample data for demonstration purposes."],
            ["Workforce", "Diversity",
             "Women held 38% of management positions in 2025, up from 32% in 2023.\n"
             "The company completed pay-equity audits across all reporting regions."],
            ["Safety", "Employee Safety",
             "The total recordable injury rate decreased by 25% compared to 2024.\n"
             "All manufacturing sites completed annual safety training in 2025."],
            ["Supply Chain", "Suppliers",
             "82% of tier-1 suppliers completed a labor-practices audit in 2025.\n"
             "The company's supplier code of conduct was updated to reference living-wage commitments."],
        ],
    },
    "company_3": {
        "company": "Northwind Energy Corp. (fictional, synthetic sample data)",
        "report_year": 2023,
        "report_title": "Northwind Energy Corp. 2023 Governance Report (synthetic sample)",
        "header": "Northwind Energy Corp. | 2023 Governance Report (SYNTHETIC SAMPLE DATA)",
        "pages": [
            ["Introduction",
             "This report summarizes Northwind Energy's 2023 governance practices.\n"
             "All figures in this document are synthetic sample data for demonstration purposes."],
            ["Board", "Board Independence",
             "Independent directors held 75% of board seats as of December 2023.\n"
             "The board's audit committee met six times during the reporting year."],
            ["Ethics", "Anti-Corruption",
             "100% of employees in scope completed anti-corruption training in 2023.\n"
             "The company recorded zero confirmed corruption incidents in 2023."],
            ["Security", "Cybersecurity",
             "The company completed an independent cybersecurity assessment in 2023.\n"
             "A formal incident-response plan was adopted covering all business units."],
        ],
    },
    "company_4": {
        "company": "Cobalt Textiles Ltd. (fictional, synthetic sample data)",
        "report_year": 2025,
        "report_title": "Cobalt Textiles Ltd. 2025 ESG Report (synthetic sample)",
        "header": "Cobalt Textiles Ltd. | 2025 ESG Report (SYNTHETIC SAMPLE DATA)",
        "pages": [
            ["Introduction",
             "This report summarizes Cobalt Textiles' 2025 environmental, social, and governance performance.\n"
             "All figures in this document are synthetic sample data for demonstration purposes."],
            ["Emissions", "Climate",
             "Scope 1 and 2 emissions combined decreased by 20% from the 2022 baseline.\n"
             "The company set a net-zero target for 2045."],
            ["Waste", "Waste Management",
             "Textile waste sent to landfill decreased by 30% in 2025.\n"
             "60% of production waste was recycled or repurposed in 2025."],
            ["Governance", "Policies",
             "The board adopted a formal human-rights policy in 2025.\n"
             "An independent grievance mechanism was established for supply-chain workers."],
        ],
    },
}


def main() -> None:
    for company_dir, spec in _REPORTS.items():
        out_dir = REPORTS_DIR / company_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        pages = [[spec["header"], *paragraphs] for paragraphs in spec["pages"]]
        pdf_path = out_dir / f"{company_dir}_esg_report.pdf"
        _build_pdf(pdf_path, pages)

        manifest = {
            "company": spec["company"], "report_year": spec["report_year"], "report_title": spec["report_title"],
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Generated {pdf_path} + manifest.json")


if __name__ == "__main__":
    main()
