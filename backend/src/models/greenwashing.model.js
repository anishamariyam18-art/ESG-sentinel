import { query } from '../config/db.js';

const createGreenwashingResult = async({ reportId, riskLevel, score, explanation }) => {
    const result = await query(
        `INSERT INTO greenwashing_results (report_id, risk_level, score, explanation)
     VALUES ($1, $2, $3, $4)
     RETURNING id, report_id, risk_level, score, explanation, created_at, updated_at`, [reportId, riskLevel, score, explanation]
    );

    return result.rows[0];
};

const findGreenwashingResultByReportId = async(reportId) => {
    const result = await query(
        `SELECT id, report_id, risk_level, score, explanation, created_at, updated_at
     FROM greenwashing_results
     WHERE report_id = $1`, [reportId]
    );

    return result.rows[0] || null;
};

export { createGreenwashingResult, findGreenwashingResultByReportId };