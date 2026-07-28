import {
    getTotalUsers,
    getTotalReports,
    getReportsGroupedByStatus,
    getAverageTrustScore,
    getAverageEsgScores,
    getGreenwashingDistribution,
    getLatestReports,
    getHistoryData,
    getStatisticsData,
    getCompanyHistoryData,
    compareYearData as compareYearDataModel,
} from "../models/dashboard.model.js";


const STATUS_KEYS = {
    completed: "completedReports",
    processing: "processingReports",
    failed: "failedReports",
};

const RISK_LEVELS = [
    "low",
    "medium",
    "high",
    "critical"
];


const buildStatusCounts = (rows) => {
    const counts = {
        completedReports: 0,
        processingReports: 0,
        failedReports: 0,
    };

    rows.forEach((row) => {
        const key = STATUS_KEYS[row.status];

        if (key) {
            counts[key] = Number(row.count);
        }
    });

    return counts;
};


const buildRiskDistribution = (rows) => {
    const result = {
        low: 0,
        medium: 0,
        high: 0,
        critical: 0,
    };

    rows.forEach((row) => {

        if (RISK_LEVELS.includes(row.risk_level)) {
            result[row.risk_level] = Number(row.count);
        }

    });

    return result;
};



const getDashboardData = async() => {

    const [
        totalUsers,
        totalReports,
        reportStatus,
        averageTrustScore,
        averageScores,
        greenwashing,
        recentReports,
    ] = await Promise.all([

        getTotalUsers(),
        getTotalReports(),
        getReportsGroupedByStatus(),
        getAverageTrustScore(),
        getAverageEsgScores(),
        getGreenwashingDistribution(),
        getLatestReports(5),

    ]);


    const status = buildStatusCounts(reportStatus);


    return {

        totalUsers,

        totalReports,

        completedReports: status.completedReports,

        processingReports: status.processingReports,

        failedReports: status.failedReports,


        averageTrustScore: Number(averageTrustScore || 0),


        averageEnvironmentalScore: Number(
            averageScores.avg_environment || 0
        ),


        averageSocialScore: Number(
            averageScores.avg_social || 0
        ),


        averageGovernanceScore: Number(
            averageScores.avg_governance || 0
        ),


        greenwashingRisk: buildRiskDistribution(greenwashing),


        recentReports,

    };
};



const getHistory = async(userId) => {

    return await getHistoryData(userId);

};



const getStatistics = async(userId) => {

    return await getStatisticsData(userId);

};



const getCompanyHistory = async(company) => {

    return await getCompanyHistoryData(company);

};



const compareYearData = async(year) => {

    return await compareYearDataModel(year);

};



export {
    getDashboardData,

    // controller expected names
    getHistory as getHistoryData,
    getStatistics as getStatisticsData,
    getCompanyHistory as getCompanyHistoryData,

    compareYearData,

    // optional aliases
    getHistory,
    getStatistics,
    getCompanyHistory,
};