import prisma from "../config/prisma.js";

export const detectGreenwashing = async (req, res) => {

  try {

    const {
      reportId,
      riskLevel,
      score,
      explanation
    } = req.body;

    const result = await prisma.greenwashingResult.create({
      data: {
        reportId,
        riskLevel,
        score,
        explanation
      }
    });

    res.status(201).json({
      success: true,
      data: result
    });

  } catch (error) {

    res.status(500).json({
      success: false,
      message: error.message
    });

  }
};