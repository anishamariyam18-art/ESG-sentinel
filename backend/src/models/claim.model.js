import { query } from '../config/db.js';

const createClaim = async({ reportId, claimText, category, pageNumber }) => {
    const result = await query(
        `INSERT INTO claims (report_id, claim_text, category, page_number)
     VALUES ($1, $2, $3, $4)
     RETURNING id, report_id, claim_text, category, page_number, created_at, updated_at`, [reportId, claimText, category, pageNumber]
    );

    return result.rows[0];
};

const findClaimsByReportId = async(reportId) => {
    const result = await query(
        `SELECT id, report_id, claim_text, category, page_number, created_at, updated_at
     FROM claims
     WHERE report_id = $1
     ORDER BY id ASC`, [reportId]
    );

    return result.rows;
};

const findClaimById = async(id) => {
    const result = await query(
        `SELECT id, report_id, claim_text, category, page_number, created_at, updated_at
     FROM claims
     WHERE id = $1`, [id]
    );

    return result.rows[0] || null;
};

export { createClaim, findClaimsByReportId, findClaimById };