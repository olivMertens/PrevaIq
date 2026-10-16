import { useMemo } from 'react';
import type { ApplicationMetadata, ExtractedField } from '@/lib/types';
import { parseDate, formatDateDisplay, getFieldData, TimelineEntry } from './lifeHealthHelpers';

export default function useLifeHealthData(application: ApplicationMetadata | null) {
  return useMemo(() => {
    const llmOutputs = (application?.llm_outputs || {}) as Record<string, any>;
    const extractedFields = application?.extracted_fields || {};
    const clinicalNotes = (llmOutputs.clinical_case_notes || {}) as Record<string, any>;
    const reasonForVisit = (clinicalNotes.reason_for_visit || {}) as Record<string, any>;
    const keyDiagnoses = (clinicalNotes.key_diagnoses || {}) as Record<string, any>;
    const files = application?.files || [];
    const documents = files.length > 0 ? files.map(f => ({ name: f.filename, type: 'Document' })) : [];

    // --- Timeline ---
    let timelineEvents: TimelineEntry[] = [];
    const llmTimeline = (llmOutputs.clinical_timeline?.treatment_timeline?.parsed?.timeline_events || []) as any[];

    if (llmTimeline.length > 0) {
      timelineEvents = llmTimeline.map((e: any) => {
        const parsedDate = parseDate(e.date);
        const displayDate = formatDateDisplay(parsedDate);
        let color: TimelineEntry['color'] = 'blue';
        const type = (e.event_type || '').toLowerCase();
        if (type.includes('diagnosis') || type.includes('condition')) color = 'red';
        else if (type.includes('procedure') || type.includes('surgery')) color = 'orange';
        else if (type.includes('visit') || type.includes('encounter')) color = 'green';
        else if (type.includes('lab') || type.includes('test')) color = 'purple';
        else if (type.includes('medication') || type.includes('rx')) color = 'yellow';
        return { date: displayDate.date, year: displayDate.year, title: e.event_type || 'Event', description: e.description, color, details: e.description, sortDate: parsedDate?.getTime() || 0 };
      });
    } else {
      const serviceDateData = getFieldData(extractedFields, ['date_of_service', 'DateOfService']);
      const serviceDate = parseDate(serviceDateData.value);
      const displayDate = formatDateDisplay(serviceDate);
      if (serviceDate) {
        const diagnosisData = getFieldData(extractedFields, ['primary_diagnosis', 'PrimaryDiagnosis']);
        const procedureData = getFieldData(extractedFields, ['procedure_name', 'ProcedureName']);
        if (diagnosisData.value) {
          timelineEvents.push({ date: displayDate.date, year: displayDate.year, title: 'Diagnosis', description: diagnosisData.value, color: 'red', details: diagnosisData.value, sortDate: serviceDate.getTime() });
        }
        if (procedureData.value) {
          timelineEvents.push({ date: displayDate.date, year: displayDate.year, title: 'Procedure', description: procedureData.value, color: 'orange', details: procedureData.value, sortDate: serviceDate.getTime() });
        }
      }
    }
    timelineEvents.sort((a, b) => (b.sortDate || 0) - (a.sortDate || 0));

    // --- Benefits ---
    const eligibility = (llmOutputs.eligibility || {}) as Record<string, any>;
    const coverageVerification = (eligibility.coverage_verification?.parsed || {}) as Record<string, any>;

    const eligibilityData = getFieldData(extractedFields, ['Eligibility', 'eligibility_status'], coverageVerification.eligibility_status || 'Active');
    const networkData = getFieldData(extractedFields, ['Network', 'network_status'], coverageVerification.network_status || 'In-Network');
    const deductibleData = getFieldData(extractedFields, ['Deductible', 'deductible_remaining'], coverageVerification.deductible_status?.remaining || '$500 met');
    const oopMaxData = getFieldData(extractedFields, ['OOPMax', 'oop_max'], '$2,100 / $6,500');
    const limitsData = getFieldData(extractedFields, ['BenefitLimits', 'limits'], 'Within Limits');

    // --- Tasks ---
    const tasks: { task: string; due: string }[] = [];
    const medicalReview = (llmOutputs.medical_review || llmOutputs.claim_assessment || {}) as Record<string, any>;
    const clinicalAssessment = (medicalReview.clinical_assessment?.parsed || medicalReview.medical_necessity_review?.parsed || {}) as Record<string, any>;
    if (clinicalAssessment.processing_action) tasks.push({ task: clinicalAssessment.processing_action, due: 'Pending' });
    const serviceReviews = clinicalAssessment.service_reviews || [];
    serviceReviews.forEach((review: any) => {
      if (review.medical_necessity === 'Review Required' || review.medical_necessity === 'Pending') {
        tasks.push({ task: `Review: ${review.service}`, due: 'Today' });
      }
    });
    const taskDecisions = (llmOutputs.tasks_decisions?.final_decision?.parsed || {}) as Record<string, any>;
    if (taskDecisions.next_steps && Array.isArray(taskDecisions.next_steps)) {
      taskDecisions.next_steps.forEach((step: string) => tasks.push({ task: step, due: 'Pending' }));
    }
    const medicalNecessity = (llmOutputs.clinical_case_notes?.medical_necessity?.parsed || {}) as Record<string, any>;
    if (medicalNecessity.services_reviewed && Array.isArray(medicalNecessity.services_reviewed)) {
      medicalNecessity.services_reviewed.forEach((review: any) => {
        if (review.necessity_status === 'Questionable' || review.necessity_status === 'Review Required') {
          tasks.push({ task: `Review: ${review.service} (${review.necessity_status})`, due: 'Today' });
        }
      });
    }

    // --- Claim Lines ---
    const claimAssessment = (llmOutputs.claim_assessment || llmOutputs.payment_calculation || {}) as Record<string, any>;
    const paymentDetermination = (claimAssessment.payment_determination?.parsed || claimAssessment.benefit_determination?.parsed || {}) as Record<string, any>;
    const paymentCalc = paymentDetermination.payment_calculation || {};
    const claimLineEval = (llmOutputs.claim_line_evaluation?.line_item_review?.parsed || {}) as Record<string, any>;
    const lineItems = paymentCalc.line_items || paymentDetermination.charge_breakdown || claimLineEval.claim_lines || [];

    // Extracted procedure codes for confidence matching
    const allExtractedProcedures: any[] = [];
    if (extractedFields) {
      Object.keys(extractedFields).forEach(key => {
        if (key.endsWith(':ProcedureCodes') || key.endsWith(':procedure_codes') || key === 'ProcedureCodes' || key === 'procedure_codes') {
          const field = extractedFields[key];
          if (field && Array.isArray(field.value)) {
            const items = field.value.map((item: any) => ({ ...item, _sourceFile: field.source_file, _pageNumber: field.page_number }));
            allExtractedProcedures.push(...items);
          }
        }
      });
    }

    const claimLines = lineItems.map((item: any) => {
      const code = item.cpt || item.code || 'N/A';
      const extracted = allExtractedProcedures.find((p: any) => {
        const pCode = p.valueObject?.code?.valueString || p.valueObject?.code?.value;
        return pCode === code;
      });
      const confidence = extracted?.valueObject?.code?.confidence;
      const citation = extracted ? { sourceFile: extracted._sourceFile, pageNumber: extracted._pageNumber, fieldName: 'ProcedureCodes', confidence } : undefined;
      return {
        line: item.line_number || item.line || 0,
        code,
        desc: item.description || item.service || item.desc || 'N/A',
        billed: item.billed || 'N/A',
        allowed: item.allowed || 'N/A',
        decision: item.ai_opinion || item.status || (paymentDetermination.claim_decision === 'Approve' ? 'Approve' : 'Pending'),
        confidence,
        citation,
      };
    });

    // --- Diagnoses extraction for confidence/citation ---
    const allExtractedDiagnoses: any[] = [];
    if (extractedFields) {
      Object.keys(extractedFields).forEach(key => {
        if (key.endsWith(':PrimaryDiagnosis') || key.endsWith(':primary_diagnosis') || key === 'PrimaryDiagnosis' || key === 'primary_diagnosis') {
          const field: ExtractedField = extractedFields[key];
          if (field?.value) allExtractedDiagnoses.push({ ...field, type: 'Primary' });
        }
        if (key.endsWith(':SecondaryDiagnoses') || key.endsWith(':secondary_diagnoses') || key === 'SecondaryDiagnoses' || key === 'secondary_diagnoses') {
          const field: ExtractedField = extractedFields[key];
          if (field && Array.isArray(field.value)) {
            field.value.forEach((item: any) => allExtractedDiagnoses.push({ ...item, _sourceFile: field.source_file, _pageNumber: field.page_number, type: 'Secondary' }));
          }
        }
      });
    }

    const getDiagnosisCitation = (code: string) => {
      const extracted = allExtractedDiagnoses.find((d: any) => {
        const dCode = d.value?.code?.valueString || d.value?.code?.value || d.valueObject?.code?.valueString || d.valueObject?.code?.value;
        return dCode === code;
      });
      if (!extracted) return undefined;
      const conf = extracted.value?.code?.confidence || extracted.valueObject?.code?.confidence;
      return {
        citation: { sourceFile: extracted.source_file || extracted._sourceFile, pageNumber: extracted.page_number || extracted._pageNumber, fieldName: extracted.type === 'Primary' ? 'PrimaryDiagnosis' : 'SecondaryDiagnoses', confidence: conf },
        confidence: conf,
      };
    };

    const reasonForVisitData = getFieldData(extractedFields, ['ReasonForVisit', 'reason_for_visit'], reasonForVisit.summary || 'Emergency room visit for acute chest pain with shortness of breath.');

    return {
      llmOutputs,
      keyDiagnoses,
      documents,
      timelineEvents,
      eligibilityData,
      networkData,
      deductibleData,
      oopMaxData,
      limitsData,
      tasks,
      claimLines,
      getDiagnosisCitation,
      reasonForVisitData,
    };
  }, [application]);
}
