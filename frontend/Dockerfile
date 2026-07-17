FROM node:24-alpine

WORKDIR /workspace
COPY turkuaz-ui/package.json ./turkuaz-ui/package.json
COPY turkuaz-ui/src ./turkuaz-ui/src
COPY report_builder/frontend/.npmrc ./report_builder/frontend/.npmrc
COPY report_builder/frontend/package.json report_builder/frontend/package-lock.json* ./report_builder/frontend/
WORKDIR /workspace/report_builder/frontend
RUN npm install
RUN ln -s /workspace/report_builder/frontend/node_modules /workspace/turkuaz-ui/node_modules
COPY report_builder/frontend ./

EXPOSE 7505
CMD ["npm", "run", "dev"]

