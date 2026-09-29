// FarmNex Crop Rescue: Flutter client. One file, depends on `dio` only.
//
// Pass the app's EXISTING Dio (the one with the FarmNex base URL and login
// token), e.g. `CropRescueApi(dio)`. The backend knows the farmer from that
// login token, so no method takes a farmer id.
//
// Field names match the backend's JSON (snake_case) exactly.

import 'package:dio/dio.dart';

double _d(dynamic v) => (v as num).toDouble();
double? _dOrNull(dynamic v) => v == null ? null : (v as num).toDouble();
DateTime _t(dynamic v) => DateTime.parse(v as String);
DateTime? _tOrNull(dynamic v) => v == null ? null : DateTime.parse(v as String);

class CropOut {
  final String code;
  final String nameEn;
  final String nameMr;
  final double refTempC;
  final double refLifeHours;
  final double lifeHoursAt25c;
  final double lifeHoursAt30c;
  final double lifeHoursAt35c;
  final String source;
  final String? note;

  CropOut({
    required this.code,
    required this.nameEn,
    required this.nameMr,
    required this.refTempC,
    required this.refLifeHours,
    required this.lifeHoursAt25c,
    required this.lifeHoursAt30c,
    required this.lifeHoursAt35c,
    required this.source,
    this.note,
  });

  factory CropOut.fromJson(Map<String, dynamic> json) => CropOut(
        code: json['code'] as String,
        nameEn: json['name_en'] as String,
        nameMr: json['name_mr'] as String,
        refTempC: _d(json['ref_temp_c']),
        refLifeHours: _d(json['ref_life_hours']),
        lifeHoursAt25c: _d(json['life_hours_at_25c']),
        lifeHoursAt30c: _d(json['life_hours_at_30c']),
        lifeHoursAt35c: _d(json['life_hours_at_35c']),
        source: json['source'] as String,
        note: json['note'] as String?,
      );
}

class CropsOut {
  final double q10;
  final String q10Note;
  final List<CropOut> crops;

  CropsOut({required this.q10, required this.q10Note, required this.crops});

  factory CropsOut.fromJson(Map<String, dynamic> json) => CropsOut(
        q10: _d(json['q10']),
        q10Note: json['q10_note'] as String,
        crops: (json['crops'] as List)
            .map((e) => CropOut.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class CheckOut {
  final String id;
  final DateTime checkedAt;
  final double temperatureC;
  final String tempSource;
  final double elapsedHours;
  final double freshnessUsed;
  final double remainingHours;
  final String status;

  CheckOut({
    required this.id,
    required this.checkedAt,
    required this.temperatureC,
    required this.tempSource,
    required this.elapsedHours,
    required this.freshnessUsed,
    required this.remainingHours,
    required this.status,
  });

  factory CheckOut.fromJson(Map<String, dynamic> json) => CheckOut(
        id: json['id'] as String,
        checkedAt: _t(json['checked_at']),
        temperatureC: _d(json['temperature_c']),
        tempSource: json['temp_source'] as String,
        elapsedHours: _d(json['elapsed_hours']),
        freshnessUsed: _d(json['freshness_used']),
        remainingHours: _d(json['remaining_hours']),
        status: json['status'] as String,
      );
}

/// status is one of: FRESH, AT_RISK, SPOILED, SOLD.
class LotOut {
  final String id;
  final String cropCode;
  final double quantityKg;
  final DateTime harvestedAt;
  final double lat;
  final double lng;
  final String storageMode;
  final double floorPricePerKg;
  final double freshnessUsed;
  final double? remainingHours;
  final DateTime? spoilEta;
  final String status;
  final DateTime lastCheckedAt;
  final DateTime createdAt;

  LotOut({
    required this.id,
    required this.cropCode,
    required this.quantityKg,
    required this.harvestedAt,
    required this.lat,
    required this.lng,
    required this.storageMode,
    required this.floorPricePerKg,
    required this.freshnessUsed,
    required this.remainingHours,
    required this.spoilEta,
    required this.status,
    required this.lastCheckedAt,
    required this.createdAt,
  });

  factory LotOut.fromJson(Map<String, dynamic> json) => LotOut(
        id: json['id'] as String,
        cropCode: json['crop_code'] as String,
        quantityKg: _d(json['quantity_kg']),
        harvestedAt: _t(json['harvested_at']),
        lat: _d(json['lat']),
        lng: _d(json['lng']),
        storageMode: json['storage_mode'] as String,
        floorPricePerKg: _d(json['floor_price_per_kg']),
        freshnessUsed: _d(json['freshness_used']),
        remainingHours: _dOrNull(json['remaining_hours']),
        spoilEta: _tOrNull(json['spoil_eta']),
        status: json['status'] as String,
        lastCheckedAt: _t(json['last_checked_at']),
        createdAt: _t(json['created_at']),
      );
}

/// A lot plus its check history (newest first).
class LotDetailOut extends LotOut {
  final List<CheckOut> checks;

  LotDetailOut({
    required super.id,
    required super.cropCode,
    required super.quantityKg,
    required super.harvestedAt,
    required super.lat,
    required super.lng,
    required super.storageMode,
    required super.floorPricePerKg,
    required super.freshnessUsed,
    required super.remainingHours,
    required super.spoilEta,
    required super.status,
    required super.lastCheckedAt,
    required super.createdAt,
    required this.checks,
  });

  factory LotDetailOut.fromJson(Map<String, dynamic> json) {
    final lot = LotOut.fromJson(json);
    return LotDetailOut(
      id: lot.id,
      cropCode: lot.cropCode,
      quantityKg: lot.quantityKg,
      harvestedAt: lot.harvestedAt,
      lat: lot.lat,
      lng: lot.lng,
      storageMode: lot.storageMode,
      floorPricePerKg: lot.floorPricePerKg,
      freshnessUsed: lot.freshnessUsed,
      remainingHours: lot.remainingHours,
      spoilEta: lot.spoilEta,
      status: lot.status,
      lastCheckedAt: lot.lastCheckedAt,
      createdAt: lot.createdAt,
      checks: (json['checks'] as List)
          .map((e) => CheckOut.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class MatchOut {
  final String buyerId;
  final String buyerName;
  final double netPricePerKg;
  final double distanceKm;
  final double travelHours;
  final double qtyKg;
  final double score;

  /// One readable line, e.g. "₹18.4/kg after transport · 12 km · 30 h to spare".
  final String reason;

  MatchOut({
    required this.buyerId,
    required this.buyerName,
    required this.netPricePerKg,
    required this.distanceKm,
    required this.travelHours,
    required this.qtyKg,
    required this.score,
    required this.reason,
  });

  factory MatchOut.fromJson(Map<String, dynamic> json) => MatchOut(
        buyerId: json['buyer_id'] as String,
        buyerName: json['buyer_name'] as String,
        netPricePerKg: _d(json['net_price_per_kg']),
        distanceKm: _d(json['distance_km']),
        travelHours: _d(json['travel_hours']),
        qtyKg: _d(json['qty_kg']),
        score: _d(json['score']),
        reason: json['reason'] as String,
      );
}

class SimulateOut {
  final List<LotOut> lots;

  SimulateOut({required this.lots});

  factory SimulateOut.fromJson(Map<String, dynamic> json) => SimulateOut(
        lots: (json['lots'] as List)
            .map((e) => LotOut.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class CheckRunOut {
  final int checked;
  final int atRisk;
  final int spoiled;

  CheckRunOut({required this.checked, required this.atRisk, required this.spoiled});

  factory CheckRunOut.fromJson(Map<String, dynamic> json) => CheckRunOut(
        checked: json['checked'] as int,
        atRisk: json['at_risk'] as int,
        spoiled: json['spoiled'] as int,
      );
}

/// kind is AT_RISK or SPOILED. For AT_RISK, `payload` holds lot_id,
/// remaining_hours and the top matches.
class AlertOut {
  final String id;
  final String lotId;
  final String kind;
  final String title;
  final String body;
  final Map<String, dynamic>? payload;
  final DateTime createdAt;
  final DateTime? readAt;

  AlertOut({
    required this.id,
    required this.lotId,
    required this.kind,
    required this.title,
    required this.body,
    required this.payload,
    required this.createdAt,
    required this.readAt,
  });

  factory AlertOut.fromJson(Map<String, dynamic> json) => AlertOut(
        id: json['id'] as String,
        lotId: json['lot_id'] as String,
        kind: json['kind'] as String,
        title: json['title'] as String,
        body: json['body'] as String,
        payload: json['payload'] as Map<String, dynamic>?,
        createdAt: _t(json['created_at']),
        readAt: _tOrNull(json['read_at']),
      );
}

class HealthOut {
  final bool ok;
  final int crops;
  final bool db;

  HealthOut({required this.ok, required this.crops, required this.db});

  factory HealthOut.fromJson(Map<String, dynamic> json) => HealthOut(
        ok: json['ok'] as bool,
        crops: json['crops'] as int,
        db: json['db'] as bool,
      );
}

class CropRescueApi {
  final Dio _dio;

  CropRescueApi(this._dio);

  Future<HealthOut> health() async {
    final r = await _dio.get('/rescue/health');
    return HealthOut.fromJson(r.data as Map<String, dynamic>);
  }

  Future<CropsOut> fetchCrops() async {
    final r = await _dio.get('/rescue/crops');
    return CropsOut.fromJson(r.data as Map<String, dynamic>);
  }

  /// [harvestedAt] is when the crop left the field. It must have a time zone
  /// and must not be in the future (the backend answers 422 otherwise).
  Future<LotOut> createLot({
    required String cropCode,
    required double quantityKg,
    required DateTime harvestedAt,
    required double lat,
    required double lng,
    String storageMode = 'ambient',
    double floorPricePerKg = 0,
    double? temperatureC,
  }) async {
    final r = await _dio.post('/rescue/lots', data: {
      'crop_code': cropCode,
      'quantity_kg': quantityKg,
      'harvested_at': harvestedAt.toUtc().toIso8601String(),
      'lat': lat,
      'lng': lng,
      'storage_mode': storageMode,
      'floor_price_per_kg': floorPricePerKg,
      if (temperatureC != null) 'temperature_c': temperatureC,
    });
    return LotOut.fromJson(r.data as Map<String, dynamic>);
  }

  Future<List<LotOut>> listLots() async {
    final r = await _dio.get('/rescue/lots');
    return (r.data as List).map((e) => LotOut.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<LotDetailOut> getLot(String lotId) async {
    final r = await _dio.get('/rescue/lots/$lotId');
    return LotDetailOut.fromJson(r.data as Map<String, dynamic>);
  }

  /// Only works while the lot is AT_RISK; otherwise the backend answers 409.
  Future<List<MatchOut>> getMatches(String lotId) async {
    final r = await _dio.get('/rescue/lots/$lotId/matches');
    return (r.data as List).map((e) => MatchOut.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<LotOut> markSold(String lotId) async {
    final r = await _dio.post('/rescue/lots/$lotId/sold');
    return LotOut.fromJson(r.data as Map<String, dynamic>);
  }

  /// Demo button. The backend answers 404 once CR_ENABLE_SIMULATE=false.
  Future<SimulateOut> simulate({
    required double hours,
    double? temperatureC,
    String? lotId,
  }) async {
    final r = await _dio.post('/rescue/simulate', data: {
      'hours': hours,
      if (temperatureC != null) 'temperature_c': temperatureC,
      if (lotId != null) 'lot_id': lotId,
    });
    return SimulateOut.fromJson(r.data as Map<String, dynamic>);
  }

  /// Poll this every 30 s on the farmer home screen.
  Future<List<AlertOut>> fetchAlerts({bool unreadOnly = false}) async {
    final r = await _dio.get(
      '/rescue/alerts',
      queryParameters: {'unread_only': unreadOnly},
    );
    return (r.data as List).map((e) => AlertOut.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<AlertOut> markAlertRead(String alertId) async {
    final r = await _dio.post('/rescue/alerts/$alertId/read');
    return AlertOut.fromJson(r.data as Map<String, dynamic>);
  }
}
