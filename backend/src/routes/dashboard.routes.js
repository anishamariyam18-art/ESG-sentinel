import express from "express";

import {
    dashboard,
    history,
    statistics,
    companyHistory,
    compareYear
} from "../controllers/dashboard.controller.js";


const router = express.Router();


// Dashboard cards + charts
router.get(
    "/dashboard",
    dashboard
);


// Logged-in user ESG history
router.get(
    "/history",
    history
);


// Logged-in user statistics
router.get(
    "/statistics",
    statistics
);


// Company history
router.get(
    "/history/:company",
    companyHistory
);


// Year comparison
router.get(
    "/compare/:year",
    compareYear
);



export default router;