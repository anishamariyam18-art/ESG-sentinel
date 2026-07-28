import logger from '../config/logger.js';
import config from '../config/env.js';

const errorMiddleware = (err, req, res, next) => {
    const statusCode = err.statusCode && Number.isInteger(err.statusCode) ? err.statusCode : 500;
    const message = statusCode === 500 && config.nodeEnv === 'production' ?
        'Internal server error' :
        err.message || 'Internal server error';

    logger.error(`${req.method} ${req.originalUrl} - ${message}`, err);

    res.status(statusCode).json({
        success: false,
        message,
    });
};

export { errorMiddleware };