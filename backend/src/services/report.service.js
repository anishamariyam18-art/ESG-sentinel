import {
    createReport,
    findReportById,
    findReportsByUserId,
    getAllReports,
    updateReportStatus,
    updateReportDetails,
    deleteReport,
    countReports,
} from '../models/report.model.js';
import { findSummaryByReportId } from '../models/summary.model.js';
import { findClaimsByReportId } from '../models/claim.model.js';
import { findEvidencesByClaimId } from '../models/evidence.model.js';
import { findVerificationByClaimId } from '../models/verification.model.js';
import { findGreenwashingResultByReportId } from '../models/greenwashing.model.js';
import { findTrustScoreByReportId } from '../models/trustscore.model.js';

const VALID_STATUSES = ['uploaded', 'processing', 'completed', 'failed'];

const ensureReportExists = async(id) => {
    const report = await findReportById(id);

    if (!report) {
        const error = new Error('Report not found');
        error.statusCode = 404;
        throw error;
    }

    return report;
};

const createNewReport = async({
    userId,
    originalFilename,
    storedFilename,
    filePath,
    fileSize,
}) => {
    if (!userId || !originalFilename || !storedFilename || !filePath || !fileSize) {
        const error = new Error('Missing required report data');
        error.statusCode = 400;
        throw error;
    }

    const report = await createReport({
        userId,
        originalFilename,
        storedFilename,
        filePath,
        fileSize,
    });

    return report;
};

const getReportById = async(id) => {
    return ensureReportExists(id);
};

const getReportsForUser = async(userId, { limit, offset } = {}) => {
    if (!userId) {
        const error = new Error('User ID is required');
        error.statusCode = 400;
        throw error;
    }

    const reports = await findReportsByUserId(userId, { limit, offset });
    const total = await countReports(userId);

    return { reports, total };
};

const getAllReportsList = async({ limit, offset } = {}) => {
    const reports = await getAllReports({ limit, offset });
    const total = await countReports();

    return { reports, total };
};

const updateStatus = async(id, status) => {
    if (!VALID_STATUSES.includes(status)) {
        const error = new Error(`Invalid status. Allowed values: ${VALID_STATUSES.join(', ')}`);
        error.statusCode = 400;
        throw error;
    }

    await ensureReportExists(id);

    const updatedReport = await updateReportStatus(id, status);

    return updatedReport;
};

const updateDetails = async(id, { originalFilename, filePath, fileSize }) => {
    await ensureReportExists(id);

    const updatedReport = await updateReportDetails(id, {
        originalFilename,
        filePath,
        fileSize,
    });

    return updatedReport;
};

const removeReport = async(id) => {
    await ensureReportExists(id);

    const deletedReport = await deleteReport(id);

    return deletedReport;
};

const buildClaimDetails = async(claim) => {
    const [verification, evidences] = await Promise.all([
        findVerificationByClaimId(claim.id),
        findEvidencesByClaimId(claim.id),
    ]);

    return {
        id: claim.id,
        claimText: claim.claim_text,
        category: claim.category,
        pageNumber: claim.page_number,
        verification: verification || {},
        evidences: evidences || [],
    };
};

const getReportDetails = async(reportId) => {
    const report = await ensureReportExists(reportId);

    const [summary, claims, greenwashing, trustScore] = await Promise.all([
        findSummaryByReportId(reportId),
        findClaimsByReportId(reportId),
        findGreenwashingResultByReportId(reportId),
        findTrustScoreByReportId(reportId),
    ]);

    const claimsWithDetails = await Promise.all(
        claims.map((claim) => buildClaimDetails(claim))
    );

    return {
        report,
        summary: summary || {},
        claims: claimsWithDetails,
        greenwashing: greenwashing || {},
        trustScore: trustScore || {},
    };
};

export {
    createNewReport,
    getReportById,
    getReportsForUser,
    getAllReportsList,
    updateStatus,
    updateDetails,
    removeReport,
    getReportDetails,
};