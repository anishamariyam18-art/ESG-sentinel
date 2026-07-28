import { pool } from "../config/db.js";
import { findReportById } from "../models/report.model.js";
import logger from "../config/logger.js";

const VALID_VERIFICATION_STATUSES = [
    "verified",
    "unverified",
    "false",
    "misleading",
];

const VALID_RISK_LEVELS = [
    "low",
    "medium",
    "high",
    "critical",
];

const VALID_CATEGORIES = [
    "environment",
    "social",
    "governance",
    "general",
];

const validateAiResponse = (aiResponse) => {
    if (!aiResponse || typeof aiResponse !== "object") {
        const error = new Error("Invalid AI response format");
        error.statusCode = 502;
        throw error;
    }

    const {
        summary,
        claims,
        greenwashing,
        trust_score: trustScore,
    } = aiResponse;

    if (!summary || typeof summary !== "object") {
        const error = new Error("AI response is missing a valid summary");
        error.statusCode = 502;
        throw error;
    }

    if (!Array.isArray(claims)) {
        const error = new Error("AI response is missing a valid claims array");
        error.statusCode = 502;
        throw error;
    }

    if (!greenwashing || typeof greenwashing !== "object") {
        const error = new Error("AI response is missing a valid greenwashing result");
        error.statusCode = 502;
        throw error;
    }

    if (!trustScore || typeof trustScore !== "object") {
        const error = new Error("AI response is missing a valid trust score");
        error.statusCode = 502;
        throw error;
    }
};

const insertSummary = async(client, reportId, summary) => {
    await client.query(
        `INSERT INTO summaries
      (report_id, summary, environment_score, social_score, governance_score)
     VALUES ($1, $2, $3, $4, $5)`, [
            reportId,
            summary.summary || summary.text || null,
            summary.environment_score || null,
            summary.social_score || null,
            summary.governance_score || null,
        ]
    );
};

const insertClaim = async(client, reportId, claim) => {
    const category = VALID_CATEGORIES.includes(claim.category) ?
        claim.category :
        "general";

    const result = await client.query(
        `INSERT INTO claims
      (report_id, claim_text, category, page_number)
     VALUES ($1, $2, $3, $4)
     RETURNING id`, [
            reportId,
            claim.claim_text,
            category,
            claim.page_number || null,
        ]
    );

    return result.rows[0].id;
};

const insertEvidences = async(client, claimId, evidences) => {
    if (!Array.isArray(evidences) || evidences.length === 0) {
        return;
    }

    for (const evidence of evidences) {
        await client.query(
            `INSERT INTO evidences
        (claim_id, source_name, source_url, evidence_text, confidence_score)
       VALUES ($1, $2, $3, $4, $5)`, [
                claimId,
                evidence.source_name,
                evidence.source_url || null,
                evidence.evidence_text,
                evidence.confidence_score || null,
            ]
        );
    }
};

const insertVerification = async(
    client,
    claimId,
    verification
) => {
    if (!verification || typeof verification !== "object") {
        return;
    }

    const status = VALID_VERIFICATION_STATUSES.includes(
            verification.verification_status
        ) ?
        verification.verification_status :
        "unverified";

    await client.query(
        `INSERT INTO verifications
      (claim_id, verification_status, confidence, reason)
     VALUES ($1, $2, $3, $4)`, [
            claimId,
            status,
            verification.confidence || null,
            verification.reason || null,
        ]
    );
};

const insertGreenwashingResult = async(
    client,
    reportId,
    greenwashing
) => {
    const riskLevel = VALID_RISK_LEVELS.includes(
            greenwashing.risk_level
        ) ?
        greenwashing.risk_level :
        "low";

    await client.query(
        `INSERT INTO greenwashing_results
      (report_id, risk_level, score, explanation)
     VALUES ($1, $2, $3, $4)`, [
            reportId,
            riskLevel,
            greenwashing.score || null,
            greenwashing.explanation || null,
        ]
    );
};
const insertTrustScore = async(client, reportId, trustScore) => {
    await client.query(
        `INSERT INTO trust_scores
      (report_id, environment_score, social_score, governance_score, overall_score)
     VALUES ($1, $2, $3, $4, $5)`, [
            reportId,
            trustScore.environment_score || null,
            trustScore.social_score || null,
            trustScore.governance_score || null,
            trustScore.overall_score || null,
        ]
    );
};

const updateReportStatusInTransaction = async(
    client,
    reportId,
    status
) => {
    await client.query(
        `UPDATE reports
     SET status = $1,
         updated_at = CURRENT_TIMESTAMP
     WHERE id = $2`, [status, reportId]
    );
};

const saveAnalysis = async(reportId, aiResponse) => {
    const report = await findReportById(reportId);

    if (!report) {
        const error = new Error("Report not found");
        error.statusCode = 404;
        throw error;
    }

    validateAiResponse(aiResponse);

    const {
        summary,
        claims,
        greenwashing,
        trust_score: trustScore,
    } = aiResponse;

    const client = await pool.connect();

    try {
        await client.query("BEGIN");

        await insertSummary(client, reportId, summary);

        for (const claim of claims) {
            if (!claim) continue;

            const claimId = await insertClaim(client, reportId, claim);

            await insertEvidences(
                client,
                claimId,
                claim.evidences
            );

            await insertVerification(
                client,
                claimId,
                claim.verification
            );
        }

        await insertGreenwashingResult(
            client,
            reportId,
            greenwashing
        );

        await insertTrustScore(
            client,
            reportId,
            trustScore
        );

        await updateReportStatusInTransaction(
            client,
            reportId,
            "completed"
        );

        await client.query("COMMIT");

        logger.info(
            `Analysis saved successfully for report ID ${reportId}`
        );
    } catch (err) {
        try {
            await client.query("ROLLBACK");
        } catch (rollbackError) {
            logger.error("Rollback failed", rollbackError);
        }

        logger.error(
            `Failed to save analysis for report ID ${reportId}`,
            err
        );

        if (err.statusCode) {
            throw err;
        }

        const error = new Error("Failed to save report analysis");
        error.statusCode = 500;
        throw error;
    } finally {
        client.release();
    }
};

export {
    saveAnalysis,
};