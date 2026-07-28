import prisma from "../config/prisma.js";

export const createGreenwashingResult = async (data) => {
  return await prisma.greenwashingResult.create({
    data
  });
};

export const getGreenwashingResults = async () => {
  return await prisma.greenwashingResult.findMany();
};