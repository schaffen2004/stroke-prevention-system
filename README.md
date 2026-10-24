# Stroke Prevention System

A data platform for reducing stroke risk by combining electronic health records
(EHR), lifestyle data, and vital-sign measurements collected over time.

## Table of Contents

1. [Introduction](#1-introduction)
   - [Problem](#11-problem)
   - [Objectives](#12-objectives)
2. [Business Domain](#2-business-domain)
3. [Data](#3-data)
   - [Data Source](#31-data-source)

## 1. Introduction

### 1.1. Problem

Stroke is a leading cause of death and long-term disability. Risk-related data
is often fragmented across medical records, lifestyle information, and
vital-sign measurements, making it difficult to identify high-risk patients and
intervene early.

### 1.2. Objectives

- Build a data platform for the stroke prevention system.
- Predict the risk of stroke.
- Provide lifestyle recommendations to reduce stroke risk.

## 2. Business Domain

The platform supports stroke prevention across the patient journey:

- **Centralized health data:** demographics, medical history, laboratory results, lifestyle, sleep, activity, and vital signs.
- **Risk prediction:** assess and stratify stroke risk to prioritize high-risk patients.
- **Lifestyle guidance:** recommend changes in smoking, alcohol, diet, sleep, and physical activity.
- **Monitoring and follow-up:** track changes, trigger alerts, and measure intervention outcomes.

## 3. Data

### 3.1. Data Source

The offline schema is defined in `src/models/offline.py`. The main data tables are:

| Table | Description | Main Fields |
|---|---|---|
| `demographic` | Patient demographic and social context | Age, gender, marital status, location, occupation, residence type, income level, family history |
| `ehr` | Clinical record and laboratory results per encounter | Height, weight, diabetes, heart disease, kidney disease, glucose, HbA1c, cholesterol, LDL, HDL |
| `lifestyle` | Lifestyle habits recorded over time | Smoking, alcohol frequency, cooking method, taste preference, diet type |
| `vital_signs` | Vital-sign measurements over time | Heart rate, SpO2, temperature, measurement time |
| `sleep_cycle` | Sleep periods and sleep quality signals | Sleep start, sleep end, sudden awakening |
| `physical_activities` | Physical-activity records | Activity type, duration, calories, distance, activity time |
| `stroke_history` | Patient stroke history | Stroke time, stroke sequence |

Each patient has one demographic record and many related health records over
time. Deleting a patient cascades to all related records.
