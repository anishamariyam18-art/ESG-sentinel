import prisma from "../config/prisma.js";

export const generateTrustScore = async (req, res) => {

  try {

    const {
      reportId,
      environmentalScore,
      socialScore,
      governanceScore,
      overallScore
    } = req.body;

    const score = await prisma.trustScore.create({
      data: {
        reportId,
        environmentalScore,
        socialScore,
        governanceScore,
        overallScore
      }
    });

    res.status(201).json({
      success: true,
      data: score
    });

  } catch (error) {

    res.status(500).json({
      success: false,
      message: error.message
    });

  }
};