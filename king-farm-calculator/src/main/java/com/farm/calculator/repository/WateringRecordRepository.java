package com.farm.calculator.repository;

import com.farm.calculator.model.Plantation;
import com.farm.calculator.model.WateringRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface WateringRecordRepository extends JpaRepository<WateringRecord, Long> {
    List<WateringRecord> findByPlantationOrderByWateredAtDesc(Plantation plantation);
}
