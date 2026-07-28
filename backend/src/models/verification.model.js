import { query } from '../config/db.js';

const createVerification = async({ claimId, verificationStatus, confidence, reason }) => {
    const result = await query(
        `INSERT INTO verifications (claim_id, verification_status, confidence, reason)
     VALUES ($1, $2, $3, $4)
     RETURNING id, claim_id, verification_status, confidence, reason, created_at, updated_at`, [claimId, verificationStatus, confidence, reason]
    );

    return result.rows[0];
};

const findVerificationByClaimId = async(claimId) => {
    const result = await query(
        `SELECT id, claim_id, verification_status, confidence, reason, created_at, updated_at
     FROM verifications
     WHERE claim_id = $1`, [claimId]
    );

    return result.rows[0] || null;
};

const updateVerification = async(id, { verificationStatus, confidence, reason }) => {
    const result = await query(
        `UPDATE verifications
     SET verification_status = COALESCE($1, verification_status),
         confidence = COALESCE($2, confidence),
         reason = COALESCE($3, reason),
         updated_at = CURRENT_TIMESTAMP
     WHERE id = $4
     RETURNING id, claim_id, verification_status, confidence, reason, created_at, updated_at`, [verificationStatus, confidence, reason, id]
    );

    return result.rows[0] || null;
};

const deleteVerification = async(id) => {
    const result = await query(
        `DELETE FROM verifications
     WHERE id = $1
     RETURNING id`, [id]
    );

    return result.rows[0] || null;
};

export { createVerification, findVerificationByClaimId, updateVerification, deleteVerification };