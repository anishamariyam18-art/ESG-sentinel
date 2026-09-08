import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import cookieParser from 'cookie-parser';

import config from './config/env.js';

import authRoutes from './routes/auth.routes.js';
import reportRoutes from './routes/report.routes.js';
import analyzerRoutes from './routes/analyzer.routes.js';
import dashboardRoutes from './routes/dashboard.routes.js';

import { notFoundMiddleware } from './middleware/notFound.js';
import { errorMiddleware } from './middleware/error.js';

const app = express();

app.disable('x-powered-by');

app.use(helmet());

app.use(
    cors({
        origin: true,
        credentials: true,
    })
);

app.use(
    morgan(
        config.nodeEnv === 'production' ?
        'combined' :
        'dev'
    )
);

app.use(express.json({ limit: '1mb' }));

app.use(
    express.urlencoded({
        extended: true,
        limit: '1mb',
    })
);

app.use(cookieParser());

app.get('/api/health', (req, res) => {
    res.status(200).json({
        success: true,
        message: 'ESG Sentinel API is running',
        environment: config.nodeEnv,
    });
});

app.use('/api/auth', authRoutes);

app.use('/api/reports', reportRoutes);

app.use('/api/analyzer', analyzerRoutes);

app.use('/api/dashboard', dashboardRoutes);

app.use(notFoundMiddleware);

app.use(errorMiddleware);

export default app;