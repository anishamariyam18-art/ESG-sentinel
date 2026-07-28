import {
    createNewReport,
    getReportById,
    getReportsForUser,
    getAllReportsList,
    updateStatus,
    removeReport,
    getReportDetails,
} from '../services/report.service.js';

const uploadReport = async(req, res, next) => {
    try {
        if (!req.file) {
            const error = new Error('No file was uploaded');
            error.statusCode = 400;
            throw error;
        }

        const report = await createNewReport({
            userId: req.user.id,
            originalFilename: req.file.originalname,
            storedFilename: req.file.filename,
            filePath: req.file.path,
            fileSize: req.file.size,
        });

        res.status(201).json({
            success: true,
            message: 'Report uploaded successfully',
            data: { report },
        });
    } catch (error) {
        next(error);
    }
};

const getReports = async(req, res, next) => {
    try {
        const { limit, offset } = req.query;

        const options = {
            limit: limit ? parseInt(limit, 10) : undefined,
            offset: offset ? parseInt(offset, 10) : undefined,
        };

        const result =
            req.user.role === 'admin' ?
            await getAllReportsList(options) :
            await getReportsForUser(req.user.id, options);

        res.status(200).json({
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

        const report = await getReportById(id);

        res.status(200).json({
            success: true,
            message: 'Report retrieved successfully',
            data: { report },
        });
    } catch (error) {
        next(error);
    }
};

const updateReportStatusHandler = async(req, res, next) => {
    try {
        const { id } = req.params;
        const { status } = req.body;

        if (!status) {
            const error = new Error('Status is required');
            error.statusCode = 400;
            throw error;
        }

        const updatedReport = await updateStatus(id, status);

        res.status(200).json({
            success: true,
            message: 'Report status updated successfully',
            data: { report: updatedReport },
        });
    } catch (error) {
        next(error);
    }
};

const deleteReportHandler = async(req, res, next) => {
    try {
        const { id } = req.params;

        await removeReport(id);

        res.status(200).json({
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
            const error = new Error('A valid report ID is required');
            error.statusCode = 400;
            throw error;
        }

        const details = await getReportDetails(id);

        res.status(200).json({
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