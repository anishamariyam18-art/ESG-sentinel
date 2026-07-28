import prisma from "../config/prisma.js";

export const createVerification = async (data) => {
  return await prisma.verification.create({
    data
  });
};

export const getVerifications = async () => {
  return await prisma.verification.findMany();
};