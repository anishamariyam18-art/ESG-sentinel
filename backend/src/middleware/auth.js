import jwt from 'jsonwebtoken';
import config from '../config/env.js';

const authenticate = (req, res, next) => {
    try {
        const authHeader = req.headers.authorization;

        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            const error = new Error('Authentication token is missing or malformed');
            error.statusCode = 401;
            throw error;
        }

        const token = authHeader.split(' ')[1];

        if (!token) {
            const error = new Error('Authentication token is missing');
            error.statusCode = 401;
            throw error;
        }

        jwt.verify(token, config.jwt.secret, (err, decoded) => {
            if (err) {
                const error = new Error(
                    err.name === 'TokenExpiredError' ?
                    'Authentication token has expired' :
                    'Invalid authentication token'
                );
                error.statusCode = 401;
                return next(error);
            }

            req.user = {
                id: decoded.id,
                email: decoded.email,
                role: decoded.role,
            };

            next();
        });
    } catch (error) {
        next(error);
    }
};

export { authenticate };