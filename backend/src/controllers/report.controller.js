import {
    createNewReport,
    getReportById,
    getReportsForUser,
    getAllReportsList,
    updateStatus,
    removeReport,
    getReportDetails,
} from '../services/report.service.js';
import { saveAnalysis } from '../services/analyzer.service.js';
import { analyzeReport } from '../services/ai.service.js';

const DEFAULT_EVIDENCE_POLICY = 'include_current_document';

const uploadReport = async(req, res, next) => {
    let report = null;

    try {
        // 1. Check uploaded file
        if (!req.file) {
            const error = new Error('No file was uploaded');
            error.statusCode = 400;
            throw error;
        }

        // 2. Read form fields
        const {
            company,
            report_year,
            evidence_policy,
        } = req.body;

        // 3. Validate company
        if (typeof company !== 'string' || !company.trim()) {
            const error = new Error('Company is required');
            error.statusCode = 400;
            throw error;
        }

        const companyName = company.trim();

        // 4. Validate report year
        const reportYear = Number(report_year);

        if (!Number.isInteger(reportYear) ||
            reportYear < 1900 ||
            reportYear > 2100
        ) {
            const error = new Error(
                'A valid report_year between 1900 and 2100 is required'
            );
            error.statusCode = 400;
            throw error;
        }

        // 5. Prepare evidence policy
        const evidencePolicy =
            typeof evidence_policy === 'string' &&
            evidence_policy.trim() ?
            evidence_policy.trim() :
            DEFAULT_EVIDENCE_POLICY;

        // 6. Create report in PostgreSQL
        report = await createNewReport({
            userId: req.user.id,
            company: companyName,
            reportYear,
            originalFilename: req.file.originalname,
            storedFilename: req.file.filename,
            filePath: req.file.path,
            fileSize: req.file.size,
        });

        // 7. Mark as processing
        await updateStatus(report.id, 'processing');

        // 8. Send PDF to FastAPI AI service
        const aiResult = await analyzeReport({
            filePath: req.file.path,
            originalFilename: req.file.originalname,
            company: companyName,
            reportYear,
            evidencePolicy,
        });
        if (
            aiResult.pipeline_status === 'failed' ||
            aiResult.pipeline_status === 'partial'
        ) {
            await updateStatus(report.id, 'failed');

            const error = new Error(
                `AI analysis failed: ${aiResult.errors?.join('; ') || 'Unknown AI pipeline error'}`
            );
            error.statusCode = 502;
            throw error;
        }

        await saveAnalysis(report.id, aiResult);

        const completedReport = await getReportById(report.id);



        // 10. Return result
        return res.status(201).json({
            success: true,
            message: 'Report uploaded and analyzed successfully',
            data: {
                report: completedReport,
                analysis: aiResult,
            },
        });

    } catch (error) {
        // If database record was created and processing failed,
        // mark the report as failed.
        if (report && report.id) {
            try {
                await updateStatus(report.id, 'failed');
            } catch (statusError) {
                console.error(
                    'Failed to update report status:',
                    statusError
                );
            }
        }

        next(error);
    }
};

const getReports = async(req, res, next) => {
    try {
        const { limit, offset } = req.query;

        const options = {
            limit: limit !== undefined ?
                Number.parseInt(limit, 10) : undefined,

            offset: offset !== undefined ?
                Number.parseInt(offset, 10) : undefined,
        };

        if (
            options.limit !== undefined &&
            (!Number.isInteger(options.limit) || options.limit < 1)
        ) {
            const error = new Error(
                'limit must be a positive integer'
            );
            error.statusCode = 400;
            throw error;
        }

        if (
            options.offset !== undefined &&
            (!Number.isInteger(options.offset) || options.offset < 0)
        ) {
            const error = new Error(
                'offset must be a non-negative integer'
            );
            error.statusCode = 400;
            throw error;
        }

        const result =
            req.user.role === 'admin' ?
            await getAllReportsList(options) :
            await getReportsForUser(req.user.id, options);

        return res.status(200).json({
            success: true,
            message: 'Reports retrieved successfully',
            data: result,
        });

    } catch (error) {
        next(error);
    }
};

const getReport = async(req, res, next) => {
    try {
        const { id } = req.params;

        if (!id || Number.isNaN(Number(id))) {
            const error = new Error(
                'A valid report ID is required'
            );
            error.statusCode = 400;
            throw error;
        }

        const report = await getReportById(id);

        return res.status(200).json({
            success: true,
            message: 'Report retrieved successfully',
            data: {
                report,
            },
        });

    } catch (error) {
        next(error);
    }
};

const updateReportStatusHandler = async(req, res, next) => {
    try {
        const { id } = req.params;
        const { status } = req.body;

        if (!id || Number.isNaN(Number(id))) {
            const error = new Error(
                'A valid report ID is required'
            );
            error.statusCode = 400;
            throw error;
        }

        if (
            typeof status !== 'string' ||
            !status.trim()
        ) {
            const error = new Error('Status is required');
            error.statusCode = 400;
            throw error;
        }

        const updatedReport = await updateStatus(
            id,
            status.trim()
        );

        return res.status(200).json({
            success: true,
            message: 'Report status updated successfully',
            data: {
                report: updatedReport,
            },
        });

    } catch (error) {
        next(error);
    }
};

const deleteReportHandler = async(req, res, next) => {
    try {
        const { id } = req.params;

        if (!id || Number.isNaN(Number(id))) {
            const error = new Error(
                'A valid report ID is required'
            );
            error.statusCode = 400;
            throw error;
        }

        await removeReport(id);

        return res.status(200).json({
            success: true,
            message: 'Report deleted successfully',
            data: {},
        });

    } catch (error) {
        next(error);
    }
};

const getReportDetailsHandler = async(req, res, next) => {
    try {
        const { id } = req.params;

        if (!id || Number.isNaN(Number(id))) {
            const error = new Error(
                'A valid report ID is required'
            );
            error.statusCode = 400;
            throw error;
        }

        const details = await getReportDetails(id);

        return res.status(200).json({
            success: true,
            data: details,
        });

    } catch (error) {
        next(error);
    }
};

export {
    uploadReport,
    getReports,
    getReport,
    updateReportStatusHandler,
    deleteReportHandler,
    getReportDetailsHandler,
};