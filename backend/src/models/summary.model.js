import { query } from '../config/db.js';

const createSummary = async ({
  reportId,
  summary,
  environmentScore,
  socialScore,
  governanceScore,
}) => {
  const result = await query(
    `INSERT INTO summaries (report_id, summary, environment_score, social_score, governance_score)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, report_id, summary, environment_score, social_score, governance_score, created_at, updated_at`,
    [reportId, summary, environmentScore, socialScore, governanceScore]
  );

  return result.rows[0];
};

const findSummaryByReportId = async (reportId) => {
  const result = await query(
    `SELECT id, report_id, summary, environment_score, social_score, governance_score, created_at, updated_at
     FROM summaries
     WHERE report_id = $1`,
    [reportId]
  );

  return result.rows[0] || null;
};

export { createSummary, findSummaryByReportId };