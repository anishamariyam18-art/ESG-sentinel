import { pool } from "../config/db.js";
import { findReportById } from "../models/report.model.js";
import logger from "../config/logger.js";

const VALID_CATEGORIES = [
    "environment",
    "social",
    "governance",
    "general",
];

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

const normalizeCategory = (category) => {
    const value = String(category || "").toLowerCase();

    if (value.includes("environment")) {
        return "environment";
    }

    if (value.includes("social")) {
        return "social";
    }

    if (value.includes("governance")) {
        return "governance";
    }

    return "general";
};

const normalizeVerificationStatus = (status) => {
    const value = String(status || "").toLowerCase();

    if (VALID_VERIFICATION_STATUSES.includes(value)) {
        return value;
    }

    if (value === "verified") {
        return "verified";
    }

    if (value === "partially_verified") {
        return "unverified";
    }

    return "unverified";
};

const normalizeRiskLevel = (risk) => {
    const value = String(risk || "").toLowerCase();

    if (VALID_RISK_LEVELS.includes(value)) {
        return value;
    }

    return "low";
};

const getRiskPriority = (risk) => {
    const priorities = {
        low: 1,
        medium: 2,
        high: 3,
        critical: 4,
    };

    return priorities[risk] || 1;
};

const getVerificationByClaimId = (verificationResults, claimId) => {
    return verificationResults.find(
        (item) => item && item.claim_id === claimId
    ) || null;
};

const getGreenwashingByClaimId = (greenwashingResults, claimId) => {
    return greenwashingResults.find(
        (item) => item && item.claim_id === claimId
    ) || null;
};

const insertSummary = async(client, reportId, analyzerResult) => {
    const summaryText =
        analyzerResult.executive_summary ||
        "Not Found";

    await client.query(
        `INSERT INTO summaries
        (
            report_id,
            summary,
            environment_score,
            social_score,
            governance_score
        )
        VALUES ($1, $2, $3, $4, $5)`, [
            reportId,
            summaryText,

            // Current AI response does not provide
            // separate numeric E/S/G scores.
            null,
            null,
            null,
        ]
    );
};

const insertClaim = async(client, reportId, claim) => {
    const category = normalizeCategory(claim.category);

    const result = await client.query(
        `INSERT INTO claims
        (
            report_id,
            claim_text,
            category,
            page_number
        )
        VALUES ($1, $2, $3, $4)
        RETURNING id`, [
            reportId,
            claim.claim || null,
            category,
            claim.page_number || null,
        ]
    );

    return result.rows[0].id;
};

const insertEvidence = async(client, claimId, evidence) => {
    if (!evidence) {
        return;
    }

    let confidenceScore = null;

    if (typeof evidence.final_score === "number") {
        confidenceScore = evidence.final_score * 100;
    }

    await client.query(
        `INSERT INTO evidences
        (
            claim_id,
            source_name,
            source_url,
            evidence_text,
            confidence_score
        )
        VALUES ($1, $2, $3, $4, $5)`, [
            claimId,
            evidence.source_type || "uploaded_report",
            null,
            evidence.evidence_text || null,
            confidenceScore,
        ]
    );
};

const insertVerification = async(
    client,
    claimId,
    verification
) => {
    if (!verification) {
        return;
    }

    const status = normalizeVerificationStatus(
        verification.status
    );

    await client.query(
        `INSERT INTO verifications
        (
            claim_id,
            verification_status,
            confidence,
            reason
        )
        VALUES ($1, $2, $3, $4)`, [
            claimId,
            status,
            verification.confidence_score || null,
            verification.reason || null,
        ]
    );
};

const insertGreenwashingResult = async(
    client,
    reportId,
    greenwashingResults
) => {
    if (!Array.isArray(greenwashingResults) ||
        greenwashingResults.length === 0
    ) {
        return;
    }

    let highestRisk = "low";
    let totalScore = 0;
    let scoreCount = 0;
    const explanations = [];

    for (const result of greenwashingResults) {
        if (!result) {
            continue;
        }

        const risk = normalizeRiskLevel(
            result.greenwashing_risk
        );

        if (
            getRiskPriority(risk) >
            getRiskPriority(highestRisk)
        ) {
            highestRisk = risk;
        }

        if (typeof result.greenwashing_score === "number") {
            totalScore += result.greenwashing_score;
            scoreCount += 1;
        }

        if (result.reason) {
            explanations.push(result.reason);
        }
    }

    const averageScore =
        scoreCount > 0 ?
        totalScore / scoreCount :
        null;

    await client.query(
        `INSERT INTO greenwashing_results
        (
            report_id,
            risk_level,
            score,
            explanation
        )
        VALUES ($1, $2, $3, $4)`, [
            reportId,
            highestRisk,
            averageScore,
            explanations.length > 0 ?
            explanations.join(" ") :
            null,
        ]
    );
};

const insertTrustScore = async(
    client,
    reportId,
    trustScore
) => {
    if (!trustScore) {
        return;
    }

    await client.query(
        `INSERT INTO trust_scores
        (
            report_id,
            environment_score,
            social_score,
            governance_score,
            overall_score
        )
        VALUES ($1, $2, $3, $4, $5)`, [
            reportId,

            // Current AI response does not provide
            // separate E/S/G scores.
            null,
            null,
            null,

            trustScore.trust_score || null,
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
        SET
            status = $1,
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

    if (!aiResponse || typeof aiResponse !== "object") {
        const error = new Error("Invalid AI response format");
        error.statusCode = 502;
        throw error;
    }

    const analyzerResult =
        aiResponse.analyzer_result || {};

    const claims =
        Array.isArray(aiResponse.claims) ?
        aiResponse.claims : [];

    const verificationResults =
        Array.isArray(aiResponse.verification_results) ?
        aiResponse.verification_results : [];

    const greenwashingResults =
        Array.isArray(aiResponse.greenwashing_results) ?
        aiResponse.greenwashing_results : [];

    const trustScore =
        aiResponse.trust_score || null;

    const client = await pool.connect();

    try {
        await client.query("BEGIN");

        await insertSummary(
            client,
            reportId,
            analyzerResult
        );

        for (const claim of claims) {
            if (!claim || !claim.claim) {
                continue;
            }

            const claimId = await insertClaim(
                client,
                reportId,
                claim
            );

            const verification =
                getVerificationByClaimId(
                    verificationResults,
                    claim.claim_id
                );

            if (
                verification &&
                Array.isArray(verification.matched_evidence)
            ) {
                for (
                    const evidence of
                    verification.matched_evidence
                ) {
                    await insertEvidence(
                        client,
                        claimId,
                        evidence
                    );
                }
            }

            await insertVerification(
                client,
                claimId,
                verification
            );
        }

        await insertGreenwashingResult(
            client,
            reportId,
            greenwashingResults
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
            logger.error(
                "Rollback failed",
                rollbackError
            );
        }

        logger.error(
            `Failed to save analysis for report ID ${reportId}`,
            err
        );

        if (err.statusCode) {
            throw err;
        }

        const error = new Error(
            "Failed to save report analysis"
        );

        error.statusCode = 500;

        throw error;
    } finally {
        client.release();
    }
};

export {
    saveAnalysis,
};