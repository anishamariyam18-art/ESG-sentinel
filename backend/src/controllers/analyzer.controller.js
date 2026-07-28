import {
    analyzeReport,
    extractClaims,
    verifyClaims,
    detectGreenwashing,
    calculateTrustScore,
} from '../services/ai.service.js';

import { saveAnalysis } from '../services/analyzer.service.js';
import { getReportById } from '../services/report.service.js';

const analyze = async(req, res, next) => {
    try {
        const { reportId } = req.params;

        if (!reportId || Number.isNaN(Number(reportId))) {
            const error = new Error('A valid report ID is required');
            error.statusCode = 400;
            throw error;
        }

        const report = await getReportById(Number(reportId));

        const analysisResult = await analyzeReport({
            filePath: report.file_path,
            originalFilename: report.original_filename,
        });

        await saveAnalysis(Number(reportId), analysisResult);

        res.status(200).json({
            success: true,
            message: 'Report analyzed and saved successfully',
            data: analysisResult,
        });
    } catch (error) {
        next(error);
    }
};

const extractClaimsHandler = async(req, res, next) => {
    try {
        const result = await extractClaims(req.body);

        res.status(200).json({
            success: true,
            message: 'Claims extracted successfully',
            data: result,
        });
    } catch (error) {
        next(error);
    }
};

const verifyClaimsHandler = async(req, res, next) => {
    try {
        const result = await verifyClaims(req.body);

        res.status(200).json({
            success: true,
            message: 'Claims verified successfully',
            data: result,
        });
    } catch (error) {
        next(error);
    }
};

const detectGreenwashingHandler = async(req, res, next) => {
    try {
        const result = await detectGreenwashing(req.body);

        res.status(200).json({
            success: true,
            message: 'Greenwashing analysis completed successfully',
            data: result,
        });
    } catch (error) {
        next(error);
    }
};

const calculateTrustScoreHandler = async(req, res, next) => {
    try {
        const result = await calculateTrustScore(req.body);

        res.status(200).json({
            success: true,
            message: 'Trust score calculated successfully',
            data: result,
        });
    } catch (error) {
        next(error);
    }
};

export {
    analyze,
    extractClaimsHandler,
    verifyClaimsHandler,
    detectGreenwashingHandler,
    calculateTrustScoreHandler,
};