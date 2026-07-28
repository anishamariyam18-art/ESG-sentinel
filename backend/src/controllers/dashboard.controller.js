import {
    getDashboardData,
    getHistoryData,
    getStatisticsData,
    getCompanyHistoryData,
    compareYearData,
} from "../services/dashboard.service.js";


// GET /api/dashboard
const getDashboard = async(req, res, next) => {
    try {

        const dashboardData = await getDashboardData();

        res.status(200).json({
            success: true,
            data: dashboardData,
        });

    } catch (error) {
        next(error);
    }
};



// GET /api/dashboard/history
const getHistory = async(req, res, next) => {
    try {

        const history = await getHistoryData();

        res.status(200).json({
            success: true,
            data: history,
        });

    } catch (error) {
        next(error);
    }
};



// GET /api/dashboard/statistics
const getStatistics = async(req, res, next) => {
    try {

        const statistics = await getStatisticsData();

        res.status(200).json({
            success: true,
            data: statistics,
        });

    } catch (error) {
        next(error);
    }
};



// GET /api/dashboard/history/:company
const getCompanyHistory = async(req, res, next) => {
    try {

        const { company } = req.params;

        const history = await getCompanyHistoryData(company);

        res.status(200).json({
            success: true,
            data: history,
        });

    } catch (error) {
        next(error);
    }
};



// GET /api/dashboard/compare/:year
const compareYear = async(req, res, next) => {
    try {

        const { year } = req.params;

        const comparison = await compareYearData(year);

        res.status(200).json({
            success: true,
            data: comparison,
        });

    } catch (error) {
        next(error);
    }
};



// Export all possible names
export {
    getDashboard,
    getHistory,
    getStatistics,
    getCompanyHistory,
    compareYear,


    // aliases for routes expecting different names
    getDashboard as dashboard,
    getHistory as history,
    getStatistics as statistics,
    getCompanyHistory as companyHistory,
};