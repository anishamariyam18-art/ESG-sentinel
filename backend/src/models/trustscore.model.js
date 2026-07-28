import { query } from '../config/db.js';

const createTrustScore = async({
    reportId,
    environmentScore,
    socialScore,
    governanceScore,
    overallScore,
}) => {
    const result = await query(
        `INSERT INTO trust_scores (report_id, environment_score, social_score, governance_score, overall_score)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, report_id, environment_score, social_score, governance_score, overall_score, generated_at, created_at, updated_at`, [reportId, environmentScore, socialScore, governanceScore, overallScore]
    );

    return result.rows[0];
};

const findTrustScoreByReportId = async(reportId) => {
    const result = await query(
        `SELECT id, report_id, environment_score, social_score, governance_score, overall_score, generated_at, created_at, updated_at
     FROM trust_scores
     WHERE report_id = $1`, [reportId]
    );

    return result.rows[0] || null;
};

export { createTrustScore, findTrustScoreByReportId };