import { query } from '../config/db.js';

const createEvidence = async({ claimId, sourceName, sourceUrl, evidenceText, confidenceScore }) => {
    const result = await query(
        `INSERT INTO evidences (claim_id, source_name, source_url, evidence_text, confidence_score)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, claim_id, source_name, source_url, evidence_text, confidence_score, created_at, updated_at`, [claimId, sourceName, sourceUrl, evidenceText, confidenceScore]
    );

    return result.rows[0];
};

const findEvidenceById = async(id) => {
    const result = await query(
        `SELECT id, claim_id, source_name, source_url, evidence_text, confidence_score, created_at, updated_at
     FROM evidences
     WHERE id = $1`, [id]
    );

    return result.rows[0] || null;
};

const findEvidencesByClaimId = async(claimId) => {
    const result = await query(
        `SELECT id, claim_id, source_name, source_url, evidence_text, confidence_score, created_at, updated_at
     FROM evidences
     WHERE claim_id = $1
     ORDER BY id ASC`, [claimId]
    );

    return result.rows;
};

const deleteEvidence = async(id) => {
    const result = await query(
        `DELETE FROM evidences
     WHERE id = $1
     RETURNING id`, [id]
    );

    return result.rows[0] || null;
};

export { createEvidence, findEvidenceById, findEvidencesByClaimId, deleteEvidence };