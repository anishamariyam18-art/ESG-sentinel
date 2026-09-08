import fs from 'fs';
import axios from 'axios';
import FormData from 'form-data';
import config from '../config/env.js';
import logger from '../config/logger.js';

const AI_REQUEST_TIMEOUT = 600000;

const handleAxiosError = (err, operation) => {
    if (axios.isAxiosError(err)) {
        if (err.code === 'ECONNABORTED') {
            logger.error(`${operation} request timed out`, err);
            const error = new Error(`${operation} request timed out`);
            error.statusCode = 504;
            throw error;
        }

        if (err.code === 'ECONNREFUSED' || !err.response) {
            logger.error(`${operation} service is unavailable`, err);
            const error = new Error(`${operation} service is currently unavailable`);
            error.statusCode = 503;
            throw error;
        }

        logger.error(
            `${operation} service responded with status ${err.response.status}`,
            err
        );

        const error = new Error(`${operation} service failed`);
        error.statusCode = 502;
        throw error;
    }

    logger.error(`Unexpected error during ${operation}`, err);

    if (err.statusCode) {
        throw err;
    }

    const error = new Error(`${operation} failed`);
    error.statusCode = 500;
    throw error;
};

const analyzeReport = async({
    filePath,
    originalFilename,
    company,
    reportYear,
    evidencePolicy = 'include_current_document',
}) => {
    if (!filePath) {
        const error = new Error('File path is required for AI analysis');
        error.statusCode = 400;
        throw error;
    }

    if (!fs.existsSync(filePath)) {
        const error = new Error(
            'Report file could not be found for analysis'
        );
        error.statusCode = 404;
        throw error;
    }

    if (!company) {
        const error = new Error(
            'Company is required for AI analysis'
        );
        error.statusCode = 400;
        throw error;
    }

    if (!reportYear) {
        const error = new Error(
            'Report year is required for AI analysis'
        );
        error.statusCode = 400;
        throw error;
    }

    const formData = new FormData();

    // PDF
    formData.append(
        'file',
        fs.createReadStream(filePath), {
            filename: originalFilename || 'report.pdf',
            contentType: 'application/pdf',
        }
    );

    // Required FastAPI form fields
    formData.append('company', company);
    formData.append('report_year', String(reportYear));
    formData.append('evidence_policy', evidencePolicy);

    try {
        const response = await axios.post(
            `${config.fastapi.baseUrl}/analyze`,
            formData, {
                headers: formData.getHeaders(),
                timeout: AI_REQUEST_TIMEOUT,
                maxBodyLength: Infinity,
                maxContentLength: Infinity,
            }
        );

        if (!response.data) {
            const error = new Error(
                'AI service returned an empty response'
            );
            error.statusCode = 502;
            throw error;
        }

        return response.data;
    } catch (err) {
        handleAxiosError(err, 'AI');
    }
};

const extractClaims = async(payload) => {
    try {
        const response = await axios.post(
            `${config.fastapi.baseUrl}/extract-claims`,
            payload, {
                timeout: AI_REQUEST_TIMEOUT,
            }
        );

        return response.data;
    } catch (err) {
        handleAxiosError(err, 'Claim extraction');
    }
};

const verifyClaims = async(payload) => {
    try {
        const response = await axios.post(
            `${config.fastapi.baseUrl}/verify-claims`,
            payload, {
                timeout: AI_REQUEST_TIMEOUT,
            }
        );

        return response.data;
    } catch (err) {
        handleAxiosError(err, 'Claim verification');
    }
};

const detectGreenwashing = async(payload) => {
    try {
        const response = await axios.post(
            `${config.fastapi.baseUrl}/greenwashing`,
            payload, {
                timeout: AI_REQUEST_TIMEOUT,
            }
        );

        return response.data;
    } catch (err) {
        handleAxiosError(err, 'Greenwashing');
    }
};

const calculateTrustScore = async(payload) => {
    try {
        const response = await axios.post(
            `${config.fastapi.baseUrl}/trust-score`,
            payload, {
                timeout: AI_REQUEST_TIMEOUT,
            }
        );

        return response.data;
    } catch (err) {
        handleAxiosError(err, 'Trust score');
    }
};

export {
    analyzeReport,
    extractClaims,
    verifyClaims,
    detectGreenwashing,
    calculateTrustScore,
};